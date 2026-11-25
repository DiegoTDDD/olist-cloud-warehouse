import datetime as dt
import hashlib
from pathlib import Path

import pytest

from pipeline import load_raw
from pipeline.contracts import RAW_TABLES, SKIPPED_FILES
from scripts.cost_report import BENCHMARK, billed, render, saving, usd
from scripts.drop_ci_datasets import to_drop

ROOT = Path(__file__).resolve().parent.parent


def test_every_source_file_has_a_contract_or_is_skipped_on_purpose():
    files = set(load_raw.expected_hashes())
    covered = {t.file for t in RAW_TABLES} | set(SKIPPED_FILES)
    assert files == covered


def test_contracts_use_only_bigquery_types_and_put_the_key_first():
    for t in RAW_TABLES:
        assert {c[1] for c in t.columns} <= {"STRING", "INT64", "NUMERIC", "DATETIME"}
        assert t.columns[0][2] == "REQUIRED", t.name
        assert len({c[0] for c in t.columns}) == len(t.columns), t.name


def test_times_are_datetime_not_timestamp():
    # Olist records local Brazilian time without a zone (ADR 0003)
    orders = next(t for t in RAW_TABLES if t.name == "orders")
    assert dict((c[0], c[1]) for c in orders.columns)["order_purchase_timestamp"] == "DATETIME"


def _fake_data(tmp_path: Path, monkeypatch) -> dict[str, str]:
    hashes = {}
    for t in RAW_TABLES:
        content = ",".join(c[0] for c in t.columns) + "\n" + ",".join("x" for _ in t.columns) + "\n"
        (tmp_path / t.file).write_text(content)
        hashes[t.file] = hashlib.sha256(content.encode()).hexdigest()
    sums = tmp_path / "sums"
    sums.write_text("".join(f"{h}  {f}\n" for f, h in hashes.items()))
    monkeypatch.setattr(load_raw, "HASHES", sums)
    return hashes


def test_plan_loads_new_tables_and_skips_unchanged_ones(tmp_path, monkeypatch):
    hashes = _fake_data(tmp_path, monkeypatch)
    orders = next(t for t in RAW_TABLES if t.name == "orders")
    existing = {"orders": hashes[orders.file], "customers": "stale"}
    actions = {a.table: a.action for a in load_raw.plan(tmp_path, existing)}
    assert actions["orders"] == "skip"
    assert actions["customers"] == "load"
    assert {a for t, a in actions.items() if t not in ("orders", "customers")} == {"load"}
    forced = {a.table: a.action for a in load_raw.plan(tmp_path, existing, force=True)}
    assert set(forced.values()) == {"load"}


def test_plan_refuses_a_file_that_does_not_match_its_hash(tmp_path, monkeypatch):
    _fake_data(tmp_path, monkeypatch)
    (tmp_path / RAW_TABLES[0].file).write_text("tampered\n")
    with pytest.raises(SystemExit, match="does not match"):
        load_raw.plan(tmp_path, {})


def test_count_records_counts_quoted_line_breaks_once(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text('﻿id,comment\n1,"line one\nline two"\n2,plain\n')
    assert load_raw.count_records(f) == 2


def test_billing_rules():
    assert billed(1) == 10 * 1024**2  # 10 MB minimum
    assert billed(25 * 1024**2 + 1) == 26 * 1024**2  # rounded up to the MB
    assert usd(1024**4) == pytest.approx(6.25)
    assert saving(25, 100) == 0.75 and saving(0, 0) is None


def test_benchmark_queries_reference_the_table_placeholder():
    for _, _, sql in BENCHMARK:
        assert "{table}" in sql


def test_render_reports_all_sections():
    report = {
        "run_at": "2026-11-25T00:00:00",
        "build": {"jobs": 3, "bytes_processed": 2 * 1024**2, "bytes_billed": 30 * 1024**2},
        "build_by_node": [{"node": "fct_orders", "jobs": 1, "bytes_processed": 1024**2, "bytes_billed": 10 * 1024**2}],
        "benchmark": [
            {"question": "q", "partitioned_bytes": 1024**2, "unpartitioned_bytes": 4 * 1024**2, "bytes_saved": 0.75}
        ],
        "storage": [{"dataset": "raw", "tables": 8, "logical_bytes": 50 * 1024**2}],
        "storage_bytes": 50 * 1024**2, "storage_share_of_sandbox": 0.0049,
    }  # fmt: skip
    md = render(report)
    assert "| fct_orders | 1 | 1.00 MB | 10.00 MB |" in md
    assert "| q | 1.00 MB | 4.00 MB | 75% |" in md
    assert "0.5% of the sandbox" in md


def test_janitor_never_touches_production_datasets():
    now = dt.datetime(2026, 11, 25, tzinfo=dt.UTC)
    old, new = now - dt.timedelta(days=2), now - dt.timedelta(hours=1)
    found = [("raw", old), ("marts", old), ("ci_pr_7_marts", old), ("ci_pr_7_staging", new), ("ci_pr_70_marts", old)]
    assert to_drop(found, "ci_pr_7", None, now) == ["ci_pr_7_marts", "ci_pr_7_staging"]
    assert to_drop(found, None, 24, now) == ["ci_pr_70_marts", "ci_pr_7_marts"]


def test_decision_report_reads_the_first_late_day():
    from scripts.decision_report import render as decision

    buckets = [
        {"delay_bucket_days": -1, "delay_bucket": "early", "orders": 80, "reviewed_orders": 79,
         "avg_review_score": 4.3, "one_star_share": 0.05},
        {"delay_bucket_days": 0, "delay_bucket": "on the promised day", "orders": 10, "reviewed_orders": 10,
         "avg_review_score": 4.0, "one_star_share": 0.08},
        {"delay_bucket_days": 1, "delay_bucket": "1 days late", "orders": 10, "reviewed_orders": 10,
         "avg_review_score": 3.0, "one_star_share": 0.3},
    ]  # fmt: skip
    months = [{"purchase_month_key": 201711, "late_rate": 0.14}, {"purchase_month_key": 201610, "late_rate": 0.9}]
    md = decision(buckets, months)
    assert "from 4.00 on the promised day to 3.00 after one day" in md
    assert "late: 10 (10.0%)" in md
    assert "14.0% in 201711" in md  # 2016 is outside the full months and ignored
