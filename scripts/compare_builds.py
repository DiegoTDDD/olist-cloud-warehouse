"""Check that an incremental build and a full rebuild of the marts hold exactly the same rows.

    python scripts/compare_builds.py --project <id> --left ci_pr_12_marts --right ci_pr_12_full_marts

The pull request build loads a few replay batches, builds, loads more (including late updates
to orders bought weeks earlier), builds again incrementally, and then rebuilds everything from
scratch into a second set of datasets. If the incremental logic ever skips a changed month or
rebuilds one wrongly, the fingerprints differ and the pull request fails.

Fingerprint of a table: its row count and the XOR of a 64-bit hash of every row's JSON. Row
order does not matter; any changed, missing or extra row does.
"""

from __future__ import annotations

import argparse
import sys

MODELS = (
    "fct_orders", "fct_order_items", "dim_customers", "dim_products", "dim_sellers", "dim_dates",
    "mart_monthly_kpis", "mart_delivery_satisfaction",
)  # fmt: skip


def fingerprint_sql(project: str, dataset: str, table: str) -> str:
    return (
        f"select count(*) as n, coalesce(bit_xor(farm_fingerprint(to_json_string(t))), 0) as fp "
        f"from `{project}.{dataset}.{table}` as t"
    )


def differences(left: dict[str, tuple[int, int]], right: dict[str, tuple[int, int]]) -> list[str]:
    out = []
    for model in sorted(set(left) | set(right)):
        a, b = left.get(model), right.get(model)
        if a != b:
            out.append(f"{model}: incremental {a} vs full rebuild {b}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    parser.add_argument("--left", required=True, help="dataset built incrementally")
    parser.add_argument("--right", required=True, help="dataset rebuilt from scratch")
    args = parser.parse_args()

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project, location=args.location)
    prints = {}
    for side in (args.left, args.right):
        prints[side] = {}
        for model in MODELS:
            row = next(iter(client.query(fingerprint_sql(args.project, side, model)).result()))
            prints[side][model] = (row["n"], row["fp"])
            print(f"{side:28} {model:28} {row['n']:>8,} rows  {row['fp']:>21}")
    diff = differences(prints[args.left], prints[args.right])
    if diff:
        print("\n".join(["The incremental build differs from the full rebuild:", *diff]))
        sys.exit(1)
    print(f"{len(MODELS)} models identical after incremental runs and after a full rebuild.")


if __name__ == "__main__":
    main()
