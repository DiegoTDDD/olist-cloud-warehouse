"""Load the Olist CSV files into the raw dataset, idempotently.

    python -m pipeline.load_raw --project <id> [--force]

For each file in pipeline/contracts.py:
1. Check its SHA-256 against scripts/olist_csv.sha256. A file that differs stops the run.
2. If the raw table already holds that exact file (the hash is stored on the table), do not load
   it again: the sandbox's 10 GiB storage allowance is for the life of the project, so
   rewriting unchanged data would spend it for nothing. Only the table's expiration is pushed
   forward (docs/adr/0001).
3. Otherwise replace the table with a load job (load jobs are free and allowed in the sandbox;
   DML is not), using the explicit schema, and check that the table has as many rows as the
   file has records.
4. Append one audit row per table to ops.load_audit, also with a load job.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline.contracts import RAW_TABLES, RawTable

ROOT = Path(__file__).resolve().parent.parent
HASHES = ROOT / "scripts" / "olist_csv.sha256"
EXPIRATION_DAYS = 59  # the sandbox caps expiration at 60 days from now; keep a day of margin

AUDIT_SCHEMA = [
    ("run_id", "STRING"), ("loaded_at", "TIMESTAMP"), ("table_name", "STRING"), ("action", "STRING"),
    ("rows", "INT64"), ("sha256", "STRING"), ("file_bytes", "INT64"),
]  # fmt: skip


@dataclass
class Action:
    table: str
    file: str
    sha256: str
    file_bytes: int
    action: str  # "load" or "skip"
    rows: int | None = None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_hashes(path: Path = HASHES) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            digest, name = line.split()
            out[name] = digest
    return out


def count_records(path: Path) -> int:
    """Records, not lines: review comments contain quoted line breaks."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def plan(data_dir: Path, existing: dict[str, str], force: bool = False) -> list[Action]:
    """Decide what to do for each table. `existing` maps table -> sha256 stored on the table."""
    wanted = expected_hashes()
    actions = []
    for t in RAW_TABLES:
        path = data_dir / t.file
        if not path.exists():
            raise SystemExit(f"missing {path}: run scripts/download_data.sh")
        digest = sha256(path)
        if digest != wanted.get(t.file):
            raise SystemExit(f"{t.file}: sha256 {digest} does not match scripts/olist_csv.sha256")
        same = existing.get(t.name) == digest
        actions.append(Action(t.name, t.file, digest, path.stat().st_size, "skip" if same and not force else "load"))
    return actions


def _schema(t: RawTable):
    from google.cloud import bigquery

    return [bigquery.SchemaField(name, kind, mode=mode) for name, kind, mode in t.columns]


def _expires() -> dt.datetime:
    return dt.datetime.now(dt.UTC) + dt.timedelta(days=EXPIRATION_DAYS)


def stored_hashes(client, dataset: str) -> dict[str, str]:
    from google.api_core.exceptions import NotFound

    out = {}
    for t in RAW_TABLES:
        try:
            table = client.get_table(f"{dataset}.{t.name}")
        except NotFound:
            continue
        # Labels are capped at 63 characters, so the full hash lives in the description.
        marker = "sha256="
        if table.description and marker in table.description:
            out[t.name] = table.description.split(marker, 1)[1].split()[0]
    return out


def load_table(client, dataset: str, t: RawTable, path: Path, digest: str) -> int:
    from google.cloud import bigquery

    table_id = f"{client.project}.{dataset}.{t.name}"
    client.delete_table(table_id, not_found_ok=True)
    config = bigquery.LoadJobConfig(
        schema=_schema(t),
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        allow_quoted_newlines=True,
        write_disposition=bigquery.WriteDisposition.WRITE_EMPTY,
        max_bad_records=0,
        labels={"pipeline": "load_raw", "table": t.name},
    )
    with path.open("rb") as f:
        client.load_table_from_file(f, table_id, job_config=config).result()
    table = client.get_table(table_id)
    expected = count_records(path)
    if table.num_rows != expected:
        raise SystemExit(f"{t.name}: loaded {table.num_rows} rows, the file has {expected} records")
    table.description = f"{t.description} Source: {t.file} sha256={digest}"
    table.labels = {"layer": "raw", "source_sha256_16": digest[:16]}
    table.expires = _expires()
    client.update_table(table, ["description", "labels", "expires"])
    return table.num_rows


def refresh_expiration(client, dataset: str) -> int:
    """Push every table's expiration forward: the sandbox would otherwise delete them."""
    n = 0
    for item in client.list_tables(dataset):
        table = client.get_table(item.reference)
        table.expires = _expires()
        client.update_table(table, ["expires"])
        n += 1
    return n


def write_audit(client, dataset: str, run_id: str, actions: list[Action]) -> None:
    from google.cloud import bigquery

    now = dt.datetime.now(dt.UTC).isoformat()
    rows = [
        {"run_id": run_id, "loaded_at": now, "table_name": a.table, "action": a.action, "rows": a.rows,
         "sha256": a.sha256, "file_bytes": a.file_bytes}
        for a in actions
    ]  # fmt: skip
    config = bigquery.LoadJobConfig(
        schema=[bigquery.SchemaField(n, k) for n, k in AUDIT_SCHEMA],
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        labels={"pipeline": "load_raw"},
    )
    data = io.BytesIO("\n".join(json.dumps(r) for r in rows).encode())
    client.load_table_from_file(data, f"{client.project}.{dataset}.load_audit", job_config=config).result()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    parser.add_argument("--dataset", default="raw")
    parser.add_argument("--ops-dataset", default="ops")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data" / "raw")
    parser.add_argument("--force", action="store_true", help="reload even if the table holds the same file")
    args = parser.parse_args(argv)

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project, location=args.location)
    run_id = uuid.uuid4().hex[:12]
    actions = plan(args.data_dir, stored_hashes(client, args.dataset), args.force)
    for a in actions:
        t = next(t for t in RAW_TABLES if t.name == a.table)
        if a.action == "load":
            a.rows = load_table(client, args.dataset, t, args.data_dir / t.file, a.sha256)
        else:
            a.rows = client.get_table(f"{args.dataset}.{a.table}").num_rows
        print(f"{a.action:4} {a.table:36} {a.rows:>9,} rows", flush=True)
    write_audit(client, args.ops_dataset, run_id, actions)
    refreshed = refresh_expiration(client, args.dataset) + refresh_expiration(client, args.ops_dataset)
    print(json.dumps({"run_id": run_id, "loaded": sum(a.action == "load" for a in actions),
                      "skipped": sum(a.action == "skip" for a in actions), "expiration_refreshed": refreshed}))  # fmt: skip
    sys.stdout.flush()


if __name__ == "__main__":
    main()

