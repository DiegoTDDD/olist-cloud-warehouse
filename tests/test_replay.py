import datetime as dt
from pathlib import Path

import pytest

from pipeline import load_raw, replay
from pipeline.contracts import RAW_TABLES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw"
KEYS = {
    "orders": ("order_id",),
    "order_items": ("order_id", "order_item_id"),
    "order_payments": ("order_id", "payment_sequential"),
    "order_reviews": ("review_id", "order_id"),
}


def order(**kw) -> dict[str, str]:
    row = {
        "order_id": "o1", "customer_id": "c1", "order_status": "delivered",
        "order_purchase_timestamp": "2018-03-01 10:00:00", "order_approved_at": "2018-03-01 11:00:00",
        "order_delivered_carrier_date": "2018-03-03 09:00:00", "order_delivered_customer_date": "2018-03-10 15:00:00",
        "order_estimated_delivery_date": "2018-03-20 00:00:00",
    }  # fmt: skip
    row.update(kw)
    return row


def test_an_order_moves_through_its_statuses_as_days_pass():
    o = order()
    assert replay.order_as_of(o, dt.date(2018, 3, 1)) is None  # not bought yet
    created = replay.order_as_of(o, dt.date(2018, 3, 2))
    assert created["order_status"] == "approved" and created["order_delivered_carrier_date"] == ""
    shipped = replay.order_as_of(o, dt.date(2018, 3, 4))
    assert shipped["order_status"] == "shipped" and shipped["order_delivered_customer_date"] == ""
    assert replay.order_as_of(o, dt.date(2018, 3, 11)) == o  # every event happened: the source row


def test_statuses_without_an_event_are_kept_once_everything_happened():
    canceled = order(order_status="canceled", order_delivered_carrier_date="", order_delivered_customer_date="")
    assert replay.order_as_of(canceled, dt.date(2018, 3, 2))["order_status"] == "canceled"
    not_approved = order(order_approved_at="2018-03-05 08:00:00", order_status="canceled",
                         order_delivered_carrier_date="", order_delivered_customer_date="")  # fmt: skip
    assert replay.order_as_of(not_approved, dt.date(2018, 3, 2))["order_status"] == "created"


def test_a_review_answer_arrives_after_the_review():
    r = {"review_id": "r1", "order_id": "o1", "review_score": "5", "review_comment_title": "",
         "review_comment_message": "", "review_creation_date": "2018-03-11 00:00:00",
         "review_answer_timestamp": "2018-03-13 08:00:00"}  # fmt: skip
    assert replay.review_as_of(r, dt.date(2018, 3, 11)) is None
    assert replay.review_as_of(r, dt.date(2018, 3, 12))["review_answer_timestamp"] == ""
    assert replay.review_as_of(r, dt.date(2018, 3, 14)) == r


def test_the_calendar_maps_each_real_day_to_one_batch_and_cycles():
    assert replay.position(replay.ANCHOR) == replay.Position(0, 0)
    assert replay.position(replay.ANCHOR - dt.timedelta(days=5)) == replay.Position(0, 0)
    assert replay.position(replay.ANCHOR + dt.timedelta(days=1)) == replay.Position(0, 1)
    last = replay.position(replay.ANCHOR + dt.timedelta(days=replay.BATCHES - 1))
    assert last == replay.Position(0, replay.BATCHES - 1) and last.as_of == replay.END
    assert replay.position(replay.ANCHOR + dt.timedelta(days=replay.BATCHES)) == replay.Position(1, 0)
    with pytest.raises(ValueError):
        replay.as_of(replay.BATCHES)


def _state(exists=True, cycle=0, last=None, source="a" * 16, layout=load_raw.LAYOUT):
    return load_raw.ChangeState(exists, cycle, last, source, layout)


SOURCES = {name: "a" * 64 for name in replay.CHANGE_TABLES}


def test_replay_plan_loads_only_the_missing_batches():
    states = {name: _state(last=4) for name in replay.CHANGE_TABLES}
    states["order_reviews"] = _state(last=2)  # a run that died halfway
    p = load_raw.plan_replay(states, replay.Position(0, 6), SOURCES)
    assert not p.full_refresh
    assert p.batches["orders"] == [5, 6] and p.batches["order_reviews"] == [3, 4, 5, 6]
    same_day = load_raw.plan_replay({n: _state(last=6) for n in replay.CHANGE_TABLES}, replay.Position(0, 6), SOURCES)
    assert not any(same_day.batches.values())


@pytest.mark.parametrize(
    "change",
    [
        {"exists": False},  # first run
        {"cycle": 1},  # the replay started over
        {"source": "b" * 16},  # a source file changed
        {"layout": None},  # a table from before the change feed
    ],
)
def test_replay_plan_resets_everything_when_the_tables_do_not_match(change):
    states = {name: _state(last=10) for name in replay.CHANGE_TABLES}
    states["orders"] = _state(**{"last": 10, **change})
    p = load_raw.plan_replay(states, replay.Position(0, 12), SOURCES)
    assert p.full_refresh
    assert all(b == list(range(13)) for b in p.batches.values())


def test_csv_for_a_batch_carries_the_batch_columns():
    rows = [order()]
    text = load_raw.to_csv("orders", rows, 3, dt.datetime(2026, 11, 26, 12, tzinfo=dt.UTC)).decode()
    header, line = text.splitlines()
    assert header.endswith(",_batch,_as_of,_loaded_at")
    assert line.endswith(",3,2018-01-04,2026-11-26T12:00:00+00:00")


needs_data = pytest.mark.skipif(not (DATA / "olist_orders_dataset.csv").exists(), reason="run scripts/download_data.sh")


@needs_data
def test_the_latest_version_of_every_record_after_the_last_batch_is_the_snapshot():
    """The property the warehouse depends on: replaying every batch and keeping the latest row
    per key rebuilds the source files exactly, with no record lost, duplicated or changed."""
    snap = replay.Snapshot(DATA, {t.name: t.file for t in RAW_TABLES})
    latest = {name: {} for name in replay.CHANGE_TABLES}
    once = {"order_items": set(), "order_payments": set()}
    for b in range(replay.BATCHES):
        for name, rows in snap.batch(b).items():
            for r in rows:
                key = tuple(r[c] for c in KEYS[name])
                if name in once:
                    assert key not in once[name], f"{name} {key} delivered twice"
                    once[name].add(key)
                latest[name][key] = r
    for name in replay.CHANGE_TABLES:
        source = {tuple(r[c] for c in KEYS[name]): r for r in snap.rows[name]}
        assert latest[name] == source, name


@needs_data
def test_batch_zero_is_2017_and_later_batches_update_older_orders():
    snap = replay.Snapshot(DATA, {t.name: t.file for t in RAW_TABLES})
    first = snap.batch(0)
    assert all(o["order_purchase_timestamp"] < "2018-01-01" for o in first["orders"])
    jan_10 = snap.batch(10)  # events of 2018-01-10
    bought_before = [o for o in jan_10["orders"] if o["order_purchase_timestamp"] < "2018-01-10"]
    assert bought_before, "deliveries of earlier orders arrive as new versions"
    assert all(i["order_id"] in {o["order_id"] for o in jan_10["orders"]} for i in jan_10["order_items"])
