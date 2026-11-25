"""Measure what the warehouse costs to build and to query, and what partitioning saves.

    python scripts/cost_report.py --project <id>

Writes reports/cost.json and reports/cost.md, and appends one row per run to ops.cost_ledger
(with a load job: the sandbox has no DML). Three measurements, all read from BigQuery itself:

1. Build: bytes processed and billed by every dbt query of the latest prod run, grouped by the
   dbt_node job label (warehouse/macros/query_comment.sql), from INFORMATION_SCHEMA.JOBS_BY_USER.
2. Queries: typical analyst questions run twice, on marts.fct_orders (partitioned by month,
   clustered by state and status) and on an unpartitioned copy made for this report, with the
   query cache off. The bytes each one reads are the measured effect of the table design.
3. Storage: logical bytes per dataset from each dataset's __TABLES__ metadata, against the
   sandbox's 10 GiB lifetime allowance.

Money is bytes times the on-demand list price (ON_DEMAND_USD_PER_TIB); the sandbox itself
bills nothing. BigQuery bills at least 10 MB per query, which the report shows separately.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"
TIB = 1024**4
MB = 1024**2
ON_DEMAND_USD_PER_TIB = 6.25  # list price, https://cloud.google.com/bigquery/pricing (Nov 2026)
MIN_BILLED_BYTES = 10 * MB
SANDBOX_STORAGE_BYTES = 10 * 1024**3
DATASETS = ("raw", "staging", "marts", "ops")

# (name, question, SQL with {table}). Filters mirror what the marts are designed for.
BENCHMARK = [
    ("one_month", "GMV and orders in one month",
     "select sum(total_payment_value) as gmv, count(*) as orders from {table} where purchase_month_key = 201711"),
    ("one_state_quarter", "Late rate in one state over a quarter",
     "select avg(cast(is_delayed as int64)) as late_rate from {table} "
     "where customer_state = 'RJ' and purchase_month_key between 201801 and 201803 and status = 'delivered'"),
    ("year_by_state", "Orders by state for a year",
     "select customer_state, count(*) as orders from {table} where purchase_month_key between 201701 and 201712 "
     "group by 1"),
    ("full_history", "Monthly late rate over the whole history (no filter: nothing to prune)",
     "select purchase_month_key, avg(cast(is_delayed as int64)) as late_rate from {table} group by 1"),
]  # fmt: skip


def usd(nbytes: float) -> float:
    return nbytes / TIB * ON_DEMAND_USD_PER_TIB


def billed(nbytes: int) -> int:
    """On-demand billing: rounded up to the MB, at least 10 MB per query."""
    return max(MIN_BILLED_BYTES, -(-nbytes // MB) * MB)


def saving(partitioned: int, flat: int) -> float | None:
    return None if not flat else round(1 - partitioned / flat, 4)


def build_costs(client, location: str) -> list[dict]:
    """Every query of the latest prod `dbt build`, found by its dbt_invocation label (each dbt
    command has its own, so docs generation and earlier runs are left out)."""
    sql = f"""
    with jobs as (
      select
        (select value from unnest(labels) where key = 'dbt_invocation') as invocation,
        (select value from unnest(labels) where key = 'dbt_node') as node,
        creation_time, total_bytes_processed, total_bytes_billed, total_slot_ms
      from `region-{location}`.INFORMATION_SCHEMA.JOBS_BY_USER
      where (select value from unnest(labels) where key = 'dbt_target') = 'prod'
        and job_type = 'QUERY' and state = 'DONE'
        and creation_time > timestamp_sub(current_timestamp(), interval 7 day)
    ),
    latest_build as (
      -- the most recent invocation that built models (docs generate only reads the catalog)
      select invocation from jobs where node = 'fct_orders' order by creation_time desc limit 1
    )
    select
      coalesce(node, 'dbt metadata queries') as node,
      count(*) as jobs,
      sum(coalesce(total_bytes_processed, 0)) as bytes_processed,
      sum(coalesce(total_bytes_billed, 0)) as bytes_billed,
      sum(coalesce(total_slot_ms, 0)) as slot_ms
    from jobs
    where invocation = (select invocation from latest_build)
    group by 1
    order by bytes_processed desc
    """
    return [dict(r) for r in client.query(sql).result()]


def run_bytes(client, sql: str) -> int:
    from google.cloud import bigquery

    config = bigquery.QueryJobConfig(use_query_cache=False, labels={"pipeline": "cost_report"},
                                     maximum_bytes_billed=1_000_000_000)  # fmt: skip
    job = client.query(sql, job_config=config)
    job.result()
    return int(job.total_bytes_processed or 0)


def benchmark(client) -> list[dict]:
    p = client.project
    client.query(
        f"create or replace table `{p}.ops.fct_orders_unpartitioned` "
        f"options (description = 'Unpartitioned copy of marts.fct_orders for scripts/cost_report.py', "
        f"expiration_timestamp = timestamp_add(current_timestamp(), interval 1 day)) "
        f"as select * from `{p}.marts.fct_orders`"
    ).result()
    rows = []
    for name, question, sql in BENCHMARK:
        part = run_bytes(client, sql.format(table=f"`{p}.marts.fct_orders`"))
        flat = run_bytes(client, sql.format(table=f"`{p}.ops.fct_orders_unpartitioned`"))
        rows.append({"query": name, "question": question, "partitioned_bytes": part, "unpartitioned_bytes": flat,
                     "bytes_saved": saving(part, flat)})  # fmt: skip
    client.delete_table(f"{p}.ops.fct_orders_unpartitioned", not_found_ok=True)
    return rows


def storage(client, location: str) -> list[dict]:
    """Logical bytes per dataset. INFORMATION_SCHEMA.TABLE_STORAGE is not enabled for new sandbox
    projects, so this reads each dataset's __TABLES__ metadata table, which always is."""
    del location  # __TABLES__ is per dataset, not per region
    parts = [
        f"select '{d}' as dataset, count(*) as tables, coalesce(sum(size_bytes), 0) as logical_bytes "
        f"from `{client.project}.{d}.__TABLES__`"
        for d in DATASETS
    ]
    return [dict(r) for r in client.query(" union all ".join(parts) + " order by dataset").result()]


def render(report: dict) -> str:
    def mb(n: float) -> str:
        return f"{n / MB:,.2f} MB"

    b = report["build"]
    lines = [
        f"# Cost report ({report['run_at'][:10]})",
        "",
        f"Prices: on-demand list price of ${ON_DEMAND_USD_PER_TIB}/TiB. The project runs in the BigQuery sandbox,",
        "so it is billed nothing; the dollars are what the same work would cost on demand.",
        "",
        "## Build (latest prod dbt run)",
        "",
        f"{b['jobs']} queries processed {mb(b['bytes_processed'])} and would bill {mb(b['bytes_billed'])} "
        f"(${usd(b['bytes_billed']):.4f} per build).",
        "",
        "| dbt node | Queries | Processed | Billed |",
        "|---|---|---|---|",
    ]
    top, rest = report["build_by_node"][:10], report["build_by_node"][10:]
    lines += [f"| {r['node']} | {r['jobs']} | {mb(r['bytes_processed'])} | {mb(r['bytes_billed'])} |" for r in top]
    if rest:
        processed, billed_bytes = sum(r["bytes_processed"] for r in rest), sum(r["bytes_billed"] for r in rest)
        jobs = sum(r["jobs"] for r in rest)
        lines.append(f"| {len(rest)} other models and tests | {jobs} | {mb(processed)} | {mb(billed_bytes)} |")
    lines += [
        "",
        "## Analyst queries: partitioned and clustered vs. unpartitioned",
        "",
        "| Question | fct_orders (partitioned) | Unpartitioned copy | Bytes saved |",
        "|---|---|---|---|",
    ]
    for r in report["benchmark"]:
        saved = "n/a" if r["bytes_saved"] is None else f"{r['bytes_saved']:.0%}"
        lines.append(f"| {r['question']} | {mb(r['partitioned_bytes'])} | {mb(r['unpartitioned_bytes'])} | {saved} |")
    lines += [
        "",
        "Billing rounds every query up to at least 10 MB, so on a table this small the bill is the same either",
        "way; the bytes read are what scale with data volume.",
        "",
        "## Storage",
        "",
        "| Dataset | Tables | Logical bytes |",
        "|---|---|---|",
    ]
    lines += [f"| {r['dataset']} | {r['tables']} | {mb(r['logical_bytes'])} |" for r in report["storage"]]
    lines += ["", f"Total {mb(report['storage_bytes'])}, {report['storage_share_of_sandbox']:.1%} of the sandbox's "
              "10 GiB lifetime allowance."]  # fmt: skip
    return "\n".join(lines) + "\n"


def write_ledger(client, report: dict) -> None:
    from google.cloud import bigquery

    row = {
        "run_at": report["run_at"], "build_bytes_processed": report["build"]["bytes_processed"],
        "build_bytes_billed": report["build"]["bytes_billed"], "build_queries": report["build"]["jobs"],
        "storage_bytes": report["storage_bytes"], "report": json.dumps(report["benchmark"]),
    }  # fmt: skip
    schema = [bigquery.SchemaField("run_at", "TIMESTAMP"), bigquery.SchemaField("build_bytes_processed", "INT64"),
              bigquery.SchemaField("build_bytes_billed", "INT64"), bigquery.SchemaField("build_queries", "INT64"),
              bigquery.SchemaField("storage_bytes", "INT64"), bigquery.SchemaField("report", "JSON")]  # fmt: skip
    config = bigquery.LoadJobConfig(schema=schema, source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
                                    write_disposition=bigquery.WriteDisposition.WRITE_APPEND)  # fmt: skip
    data = io.BytesIO(json.dumps(row).encode())
    client.load_table_from_file(data, f"{client.project}.ops.cost_ledger", job_config=config).result()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    args = parser.parse_args()

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project, location=args.location)
    by_node = build_costs(client, args.location)
    totals = {k: sum(int(r[k]) for r in by_node) for k in ("jobs", "bytes_processed", "bytes_billed", "slot_ms")}
    store = storage(client, args.location)
    total_storage = sum(int(r["logical_bytes"] or 0) for r in store)
    report = {
        "run_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "price_usd_per_tib": ON_DEMAND_USD_PER_TIB,
        "build": totals,
        "build_by_node": by_node,
        "benchmark": benchmark(client),
        "storage": store,
        "storage_bytes": total_storage,
        "storage_share_of_sandbox": total_storage / SANDBOX_STORAGE_BYTES,
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "cost.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    (REPORTS / "cost.md").write_text(render(report))
    write_ledger(client, report)
    print(render(report))


if __name__ == "__main__":
    main()
