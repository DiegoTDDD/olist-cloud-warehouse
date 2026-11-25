"""Delete the throwaway datasets of pull request builds.

    python scripts/drop_ci_datasets.py --project <id> --prefix ci_pr_12     # one pull request
    python scripts/drop_ci_datasets.py --project <id> --older-than-hours 24  # janitor

Only datasets whose name starts with ci_ are ever touched, so a wrong prefix cannot reach
raw, staging, marts or ops.
"""

from __future__ import annotations

import argparse
import datetime as dt


def to_drop(datasets: list[tuple[str, dt.datetime]], prefix: str | None, older_than_hours: float | None,
            now: dt.datetime) -> list[str]:  # fmt: skip
    out = []
    for name, created in datasets:
        if not name.startswith("ci_"):
            continue
        if prefix is not None and not name.startswith(prefix + "_"):
            continue
        if older_than_hours is not None and now - created < dt.timedelta(hours=older_than_hours):
            continue
        out.append(name)
    return sorted(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--prefix")
    parser.add_argument("--older-than-hours", type=float)
    args = parser.parse_args()
    if args.prefix is None and args.older_than_hours is None:
        parser.error("give --prefix or --older-than-hours")
    if args.prefix is not None and not args.prefix.startswith("ci_"):
        parser.error("--prefix must start with ci_")

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project)
    found = []
    for item in client.list_datasets():
        if item.dataset_id.startswith("ci_"):
            found.append((item.dataset_id, client.get_dataset(item.reference).created))
    for name in to_drop(found, args.prefix, args.older_than_hours, dt.datetime.now(dt.UTC)):
        client.delete_dataset(f"{args.project}.{name}", delete_contents=True, not_found_ok=True)
        print(f"dropped {name}")


if __name__ == "__main__":
    main()
