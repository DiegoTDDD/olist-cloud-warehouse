"""The decision report renders at any point of the replay, including the first days."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "decision_report", Path(__file__).resolve().parents[1] / "scripts" / "decision_report.py"
)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def bucket(days, orders, score, one_star):
    name = "early" if days < 0 else "on the promised day" if days == 0 else f"{days} days late"
    return {"delay_bucket": name, "delay_bucket_days": days, "orders": orders,
            "reviewed_orders": orders, "avg_review_score": score, "one_star_share": one_star}  # fmt: skip


BUCKETS = [bucket(-1, 900, 4.3, 0.06), bucket(0, 50, 4.0, 0.08), bucket(1, 30, 3.7, 0.12),
           bucket(3, 20, 2.7, 0.4), bucket(6, 10, 1.8, 0.66), bucket(10, 10, 1.75, 0.68)]  # fmt: skip


def test_a_month_with_no_deliveries_yet_does_not_break_the_report():
    # The deploy of 2026-11-27 failed here: January 2018 had orders but no deliveries yet.
    months = [{"purchase_month_key": 201710, "late_rate": 0.05},
              {"purchase_month_key": 201711, "late_rate": 0.087},
              {"purchase_month_key": 201801, "late_rate": None}]  # fmt: skip
    early = report.render(BUCKETS, months, "2018-01-02")
    assert "peaked at 5.0% in 201710" in early  # November is still waiting for deliveries
    later = report.render(BUCKETS, months, "2018-03-01")
    assert "peaked at 8.7% in 201711" in later and "to 2017-12" in later


def test_missing_buckets_and_ratings_are_left_out():
    sparse = [bucket(-1, 10, 4.5, 0.0), {**bucket(2, 0, None, None)}]
    text = report.render(sparse, [], "2018-01-01")
    assert "Not enough delivered and reviewed orders" in text
    assert "None" not in text


def test_the_full_history_uses_the_months_through_august_2018():
    months = [{"purchase_month_key": m, "late_rate": 0.01 * (m % 100)} for m in (201701, 201808, 201809)]
    assert "peaked at 8.0% in 201808" in report.render(BUCKETS, months)


def test_last_settled_month():
    assert report.last_settled_month("2018-01-02") == 201710
    assert report.last_settled_month("2018-10-30") == 201807
    assert report.last_settled_month(None) == 201808
