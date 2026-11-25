"""Write the decision the warehouse exists to support: what each day of delay costs in rating.

    python scripts/decision_report.py --project <id>

Reads marts.mart_delivery_satisfaction and marts.mart_monthly_kpis and writes
reports/decision.md and reports/decision.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(buckets: list[dict], months: list[dict]) -> str:
    on_time = [b for b in buckets if b["delay_bucket_days"] <= 0]
    late = [b for b in buckets if b["delay_bucket_days"] > 0]
    on_time_orders = sum(b["orders"] for b in on_time)
    late_orders = sum(b["orders"] for b in late)
    first_late = next(b for b in buckets if b["delay_bucket_days"] == 1)
    promised_day = next(b for b in buckets if b["delay_bucket_days"] == 0)
    lines = [
        "# Decision: where should logistics money go?",
        "",
        f"Delivered orders that arrived on time or early: {on_time_orders:,}; late: {late_orders:,} "
        f"({late_orders / (on_time_orders + late_orders):.1%}).",
        "",
        f"The rating falls from {promised_day['avg_review_score']:.2f} on the promised day to "
        f"{first_late['avg_review_score']:.2f} one day late, and the 1-star share rises from "
        f"{promised_day['one_star_share']:.1%} to {first_late['one_star_share']:.1%}. Most of the damage happens "
        "on the first day, so avoiding delays is worth more than shortening long ones.",
        "",
        "| Delivery | Orders | Reviewed | Average rating | 1-star share |",
        "|---|---|---|---|---|",
    ]
    for b in buckets:
        lines.append(f"| {b['delay_bucket']} | {b['orders']:,} | {b['reviewed_orders']:,} | "
                     f"{b['avg_review_score']:.2f} | {b['one_star_share']:.1%} |")  # fmt: skip
    full = [m for m in months if 201701 <= m["purchase_month_key"] <= 201808]
    worst = max(full, key=lambda m: m["late_rate"])
    lines += [
        "",
        f"Late rate by purchase month peaked at {worst['late_rate']:.1%} in {worst['purchase_month_key']} "
        "(full months 2017-01 to 2018-08). Correlation in observational data: late orders may differ in other ways.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="southamerica-east1")
    args = parser.parse_args()

    from google.cloud import bigquery

    client = bigquery.Client(project=args.project, location=args.location)
    p = args.project
    buckets = [dict(r) for r in client.query(
        f"select * from `{p}.marts.mart_delivery_satisfaction` order by delay_bucket_days").result()]  # fmt: skip
    months = [dict(r) for r in client.query(
        f"select purchase_month_key, late_rate from `{p}.marts.mart_monthly_kpis` order by 1").result()]  # fmt: skip
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "decision.json").write_text(json.dumps({"buckets": buckets, "months": months}, indent=2, default=str))
    (out / "decision.md").write_text(render(buckets, months))
    print(render(buckets, months))


if __name__ == "__main__":
    main()
