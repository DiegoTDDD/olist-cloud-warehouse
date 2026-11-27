"""Load the Olist data into the raw dataset, idempotently, as a daily change feed.

    python -m pipeline.load_raw --project <id> [--today YYYY-MM-DD] [--until-batch N] [--force]

Every source file is checked against its SHA-256 in scripts/olist_csv.sha256 first; a file that
differs stops the run. Then:

Reference tables (customers, products, sellers, category names) are loaded whole. A table that
already holds that exact file (its hash is stored on the table) is not loaded again: the sandbox
gives 10 GiB of storage, and rewriting unchanged data would spend it for nothing.

Change tables (orders, order_items, order_payments, order_reviews) receive the daily replay
(pipeline/replay.py, docs/adr/0006). The real date says which batch the warehouse should have;
every batch from the last one loaded up to that one is loaded, so a run after an outage catches
up by itself. Each batch goes into its own partition (`table$<batch>`) with a load job that
replaces that partition only: running the same batch twice gives the same table. Load jobs are
free and allowed in the sandbox; DML is not (docs/adr/0001).

A new replay cycle, a changed source file or a table in an older layout resets the change
tables and asks for a dbt full refresh (printed, and written to $GITHUB_OUTPUT as
full_refresh=true).

One audit row per table goes to ops.load_audit, also with a load job.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from pipeline import replay
from pipeline.contracts import BATCH_COLUMNS, RAW_TABLES, RawTable

ROOT = Path(__file__).resolve().parent.parent
HASHES = ROOT / "scripts" / "olist_csv.sha256"
EXPIRATION_DAYS = 59  # the sandbox caps expiration at 60 days from now; keep a day of margin
MIN_BATCH_SECONDS = 2.5
LAYOUT = "replay-v1"  # bump when the change tables' layout changes: forces a reset

AUDIT_SCHEMA = [
    ("run_id", "STRING"), ("loaded_at", "TIMESTAMP"), ("table_name", "STRING"), ("action", "STRING"),
    ("rows", "INT64"), ("sha256", "STRING"), ("file_bytes", "INT64"),
    ("batch_from", "INT64"), ("batch_to", "INT64"), ("as_of", "DATE"),
]  # fmt: skip


@dataclass
class Action:
    table: str
    file: str
    sha256: str
    file_bytes: int
    action: str  # "load" or "skip"
    rows: int | None = None


@dataclass
class ChangeState:
    """What a change table holds, read from its labels."""

    exists: bool
    cycle: int | None = None
    last_batch: int | None = None
    source: str | None = None  # first 16 hex digits of the source file's SHA-256
    layout: str | None = None


@dataclass
class ReplayPlan:
    reset: bool
    batches: dict[str, list[int]] = field(default_factory=dict)

    @property
    def full_refresh(self) -> bool:
        return self.reset


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_hashes(path: Path | None = None) -> dict[str, str]:
    out = {}
    for line in (path or HASHES).read_text().splitlines():
        if line.strip():
            digest, name = line.split()
            out[name] = digest
    return out


def count_records(path: Path) -> int:
    """Records, not lines: review comments contain quoted line breaks."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.reader(f)) - 1


def verify(data_dir: Path) -> dict[str, str]:
    """SHA-256 of every source file, after checking it against the pinned list."""
    wanted = expected_hashes()
    out = {}
    for t in RAW_TABLES:
        path = data_dir / t.file
        if not path.exists():
            raise SystemExit(f"missing {path}: run scripts/download_data.sh")
        digest = sha256(path)
        if digest != wanted.get(t.file):
            raise SystemExit(f"{t.file}: sha256 {digest} does not match scripts/olist_csv.sha256")
        out[t.name] = digest
    return out


def plan(data_dir: Path, existing: dict[str, str], force: bool = False) -> list[Action]:
    """What to do with each reference table. `existing` maps table -> sha256 stored on it."""
    digests = verify(data_dir)
    actions = []
    for t in RAW_TABLES:
        if t.name in replay.CHANGE_TABLES:
            continue
        same = existing.get(t.name) == digests[t.name]
        size = (data_dir / t.file).stat().st_size
        actions.append(Action(t.name, t.file, digests[t.name], size, "skip" if same and not force else "load"))
    return actions


def plan_replay(states: dict[str, ChangeState], target: replay.Position, sources: dict[str, str]) -> ReplayPlan:
    """Which batches each change table still needs to reach `target`, and whether to reset.

    Reset when any table is missing, belongs to another cycle, was built from another source
    file or in another layout: the change tables must always describe one consistent replay.
    """
    reset = any(
        not s.exists or s.cycle != target.cycle or s.source != sources[name][:16] or s.layout != LAYOUT
        for name, s in states.items()
    )
    batches = {}
    for name, s in states.items():
        start = 0 if reset or s.last_batch is None else s.last_batch + 1
        batches[name] = list(range(start, target.batch + 1))
    return ReplayPlan(reset, batches)


def _schema(columns):
    from google.cloud import bigquery

    return [bigquery.SchemaField(name, kind, mode=mode) for name, kind, mode in columns]


def _expires() -> dt.datetime:
    return dt.datetime.now(dt.UTC) + dt.timedelta(days=EXPIRATION_DAYS)


def _contract(name: str) -> RawTable:
    return next(t for t in RAW_TABLES if t.name == name)


def stored_hashes(client, dataset: str) -> dict[str, str]:
    from google.api_core.exceptions import NotFound

    out = {}
    for t in RAW_TABLES:
        if t.name in replay.CHANGE_TABLES:
            continue
        try:
            table = client.get_table(f"{dataset}.{t.name}")
        except NotFound:
            continue
        # Labels are capped at 63 characters, so the full hash lives in the description.
        marker = "sha256="
        if table.description and marker in table.description:
            out[t.name] = table.description.split(marker, 1)[1].split()[0]
    return out


def change_states(client, dataset: str) -> dict[str, ChangeState]:
    from google.api_core.exceptions import NotFound

    out = {}
    for name in replay.CHANGE_TABLES:
        try:
            labels = client.get_table(f"{dataset}.{name}").labels or {}
        except NotFound:
            out[name] = ChangeState(False)
            continue
        out[name] = ChangeState(
            True,
            int(labels["replay_cycle"]) if "replay_cycle" in labels else None,
            int(labels["replay_batch"]) if "replay_batch" in labels else None,
            labels.get("source_sha256_16"),
            labels.get("layout"),
        )
    return out


def load_table(client, dataset: str, t: RawTable, path: Path, digest: str) -> int:
    from google.cloud import bigquery

    table_id = f"{client.project}.{dataset}.{t.name}"
    client.delete_table(table_id, not_found_ok=True)
    config = bigquery.LoadJobConfig(
        schema=_schema(t.columns),
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


def create_change_table(client, dataset: str, name: str, cycle: int, source: str) -> None:
    """(Re)create a change table: integer-range partitioned on _batch, clustered on its key."""
    from google.cloud import bigquery

    t = _contract(name)
    table_id = f"{client.project}.{dataset}.{name}"
    client.delete_table(table_id, not_found_ok=True)
    table = bigquery.Table(table_id, schema=_schema(t.columns + BATCH_COLUMNS))
    table.range_partitioning = bigquery.RangePartitioning(
        field="_batch", range_=bigquery.PartitionRange(start=0, end=replay.BATCHES, interval=1)
    )
    table.clustering_fields = [t.key]
    table.description = (
        f"{t.description} Change feed: one row per version of a record, as the daily replay delivered it "
        f"(pipeline/replay.py). Source: {t.file}."
    )
    table.labels = {"layer": "raw", "source_sha256_16": source[:16], "replay_cycle": str(cycle), "layout": LAYOUT}
    table.expires = _expires()
    client.create_table(table)


def to_csv(name: str, rows: list[dict[str, str]], batch: int, loaded_at: dt.datetime) -> bytes:
    t = _contract(name)
    columns = [c[0] for c in t.columns]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(columns + [c[0] for c in BATCH_COLUMNS])
    extra = [batch, replay.as_of(batch).isoformat(), loaded_at.isoformat()]
    for r in rows:
        w.writerow([r[c] for c in columns] + extra)
    return buf.getvalue().encode()


def load_batch(client, dataset: str, name: str, rows: list[dict[str, str]], batch: int) -> int:
    """Replace partition `batch` of a change table with these rows; returns rows written."""
    from google.cloud import bigquery

    t = _contract(name)
    config = bigquery.LoadJobConfig(
        schema=_schema(t.columns + BATCH_COLUMNS),
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        allow_quoted_newlines=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # this partition only
        max_bad_records=0,
        labels={"pipeline": "load_raw", "table": name, "replay_batch": str(batch)},
    )
    if rows:
        data = io.BytesIO(to_csv(name, rows, batch, dt.datetime.now(dt.UTC)))
        job = client.load_table_from_file(data, f"{client.project}.{dataset}.{name}${batch}", job_config=config)
        job.result()
        if job.output_rows != len(rows):
            raise SystemExit(f"{name} batch {batch}: loaded {job.output_rows} rows, expected {len(rows)}")
    return len(rows)


def mark_loaded(client, dataset: str, name: str, batch: int) -> None:
    """Record the last batch on the table. Done once per run, not per batch: BigQuery allows five
    metadata updates per table every ten seconds, and each load job already counts as one. If a
    run dies before this, the next one reloads from the previous mark, which is harmless because
    every batch load replaces its own partition."""
    table = client.get_table(f"{dataset}.{name}")
    table.labels = {**(table.labels or {}), "replay_batch": str(batch)}
    client.update_table(table, ["labels"])


def run_replay(client, dataset: str, data_dir: Path, target: replay.Position, sources: dict[str, str]):
    """Bring the change tables to `target`. Returns (plan, rows loaded per table)."""
    p = plan_replay(change_states(client, dataset), target, sources)
    if p.reset:
        for name in replay.CHANGE_TABLES:
            create_change_table(client, dataset, name, target.cycle, sources[name])
    rows = {name: 0 for name in replay.CHANGE_TABLES}
    if not any(p.batches.values()):
        return p, rows
    snapshot = replay.Snapshot(data_dir, {t.name: t.file for t in RAW_TABLES})
    for b in sorted({b for bs in p.batches.values() for b in bs}):
        started = time.monotonic()
        feed = snapshot.batch(b)
        todo = [n for n in replay.CHANGE_TABLES if b in p.batches[n]]
        with ThreadPoolExecutor(len(todo)) as pool:
            futures = {n: pool.submit(load_batch, client, dataset, n, feed[n], b) for n in todo}
            for n, future in futures.items():
                rows[n] += future.result()
        print(f"batch {b:3} (as of {replay.as_of(b)}): " + ", ".join(f"{n} {len(feed[n])}" for n in todo), flush=True)
        # At most one load per table every 2.5 s keeps catch-ups under the metadata update limit.
        time.sleep(max(0.0, MIN_BATCH_SECONDS - (time.monotonic() - started)))
    for name, batches in p.batches.items():
        if batches:
            mark_loaded(client, dataset, name, batches[-1])
    return p, rows


RENEW_WITHIN_DAYS = 30  # extend a table's expiration once it is less than this far away


def refresh_expiration(client, dataset: str, now: dt.datetime | None = None) -> int:
    """Keep every table of a dataset alive: the sandbox deletes a table when it expires.

    Tables whose expiration is still more than RENEW_WITHIN_DAYS away are left alone (no
    metadata update). The others get a new expiration; if the sandbox refuses it (it rejected
    an extension on 2026-11-27 with "must be less than 60 days"), the table is renewed by copy,
    which gives it a new creation time. Views are skipped: dbt recreates them every run.
    Returns the number of tables extended or renewed.
    """
    from google.api_core.exceptions import Forbidden

    now = now or dt.datetime.now(dt.UTC)
    n = 0
    for item in client.list_tables(dataset):
        if item.table_type != "TABLE" or item.table_id.endswith(RENEW_SUFFIX):
            continue
        table = client.get_table(item.reference)
        if table.expires and table.expires > now + dt.timedelta(days=RENEW_WITHIN_DAYS):
            continue
        table.expires = _expires()
        try:
            client.update_table(table, ["expires"])
        except Forbidden as e:
            print(f"expiration of {dataset}.{item.table_id} refused ({e.message[:80]}); renewing by copy", flush=True)
            renew_by_copy(client, table)
        n += 1
    return n


RENEW_SUFFIX = "__renew"


def renew_by_copy(client, table) -> None:
    """Recreate a table from a copy of itself, so it gets a new creation time and expiration.

    The original is deleted only after the copy has succeeded, and the copy only after the
    table is back, so a failure at any point leaves the data in one of the two tables.
    """
    from google.cloud import bigquery

    ref = f"{table.project}.{table.dataset_id}.{table.table_id}"
    tmp = ref + RENEW_SUFFIX
    truncate = bigquery.CopyJobConfig(write_disposition="WRITE_TRUNCATE")
    client.copy_table(ref, tmp, job_config=truncate).result()
    client.delete_table(ref)
    client.copy_table(tmp, ref, job_config=truncate).result()
    client.delete_table(tmp)
    renewed = client.get_table(ref)
    renewed.description, renewed.labels, renewed.expires = table.description, table.labels, _expires()
    client.update_table(renewed, ["description", "labels", "expires"])


def ensure_datasets(client, project: str, location: str, names) -> None:
    """Create missing datasets. In production Terraform owns them and the deployer cannot
    create datasets at all; pull request builds create their own ci_pr_<n>_raw and _ops."""
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    for name in names:
        try:
            client.get_dataset(f"{project}.{name}")
        except NotFound:
            ds = bigquery.Dataset(f"{project}.{name}")
            ds.location = location
            client.create_dataset(ds)


def write_audit(client, dataset: str, rows: list[dict]) -> None:
    from google.cloud import bigquery

    config = bigquery.LoadJobConfig(
        schema=[bigquery.SchemaField(n, k) for n, k in AUDIT_SCHEMA],
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
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
    parser.add_argument("--today", type=dt.date.fromisoformat, help="real date to load for (default: today, UTC)")
    parser.add_argument("--until-batch", type=int, help="load up to this batch of cycle 0 (tests and backfills)")
    parser.add_argument("--force", action="store_true", help="reload reference tables even if unchanged")
    args = parser.parse_args(argv)

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project, location=args.location)
    ensure_datasets(client, args.project, args.location, (args.dataset, args.ops_dataset))
    run_id = uuid.uuid4().hex[:12]
    now = dt.datetime.now(dt.UTC).isoformat()
    sources = verify(args.data_dir)
    if args.until_batch is not None:
        target = replay.Position(0, args.until_batch)
    else:
        target = replay.position(args.today or dt.datetime.now(dt.UTC).date())

    audit = []
    for a in plan(args.data_dir, stored_hashes(client, args.dataset), args.force):
        if a.action == "load":
            a.rows = load_table(client, args.dataset, _contract(a.table), args.data_dir / a.file, a.sha256)
        else:
            a.rows = client.get_table(f"{args.dataset}.{a.table}").num_rows
        print(f"{a.action:4} {a.table:36} {a.rows:>9,} rows", flush=True)
        audit.append({"run_id": run_id, "loaded_at": now, "table_name": a.table, "action": a.action,
                      "rows": a.rows, "sha256": a.sha256, "file_bytes": a.file_bytes})  # fmt: skip

    p, rows = run_replay(client, args.dataset, args.data_dir, target, sources)
    for name in replay.CHANGE_TABLES:
        if p.batches[name]:
            audit.append({"run_id": run_id, "loaded_at": now, "table_name": name, "action": "replay",
                          "rows": rows[name], "sha256": sources[name],
                          "batch_from": p.batches[name][0], "batch_to": p.batches[name][-1],
                          "as_of": target.as_of.isoformat()})  # fmt: skip
    write_audit(client, args.ops_dataset, audit)
    # Every dataset, dbt's included: an incremental model is never recreated, so it expires too.
    refreshed = sum(refresh_expiration(client, d.dataset_id) for d in client.list_datasets())
    summary = {"run_id": run_id, "cycle": target.cycle, "batch": target.batch, "as_of": target.as_of.isoformat(),
               "full_refresh": p.full_refresh, "rows": rows, "expiration_refreshed": refreshed}  # fmt: skip
    print(json.dumps(summary))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"full_refresh={str(p.full_refresh).lower()}\nas_of={target.as_of}\nbatch={target.batch}\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
