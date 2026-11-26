"""Replay the Olist snapshot as data that arrives one day at a time.

The Olist files are a finished 2016-2018 snapshot. A warehouse in production never sees one:
orders are created, approved, shipped and delivered on different days, reviews come weeks
later, and an order's row changes every time. To run the warehouse the way it would run in
production, the loader replays the snapshot as a daily change feed (docs/adr/0006):

* Batch 0 is the state of the business as known at the start of 2018-01-01: every order bought
  before that, with only the events that had already happened.
* Batch b (b >= 1) covers simulated day 2018-01-01 + (b - 1): every order or review that had an
  event that day, with its full row as known at the end of the day. An order bought in March
  and delivered in April appears twice: once in March as "approved" with no delivery date,
  once in April as "delivered".
* Items and payments arrive once, in the batch of the order's purchase day.
* After the last batch, every order and review is in its final state, so the latest row per key
  over all batches equals the snapshot exactly (tests/test_replay.py checks this).

The real calendar drives the simulated one: each real day is one batch, starting at ANCHOR.
When the replay reaches the end it starts a new cycle from batch 0, which the loader treats as
a full reset (raw change tables recreated, dbt --full-refresh).
"""

from __future__ import annotations

import csv
import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

START = dt.date(2018, 1, 1)  # as-of date of batch 0
# Batch b is known as of START + b days. The last event in the files (a review answer) is on
# 2018-10-29, so the batch known as of 2018-10-30 is the final state.
END = dt.date(2018, 10, 30)
BATCHES = (END - START).days + 1  # batches 0..BATCHES-1 make one cycle
ANCHOR = dt.date(2026, 11, 26)  # real day that loads batch 0 of cycle 0

ORDER_EVENTS = (  # (column, status the order has once this event happened)
    ("order_approved_at", "approved"),
    ("order_delivered_carrier_date", "shipped"),
    ("order_delivered_customer_date", "delivered"),
)
CHANGE_TABLES = ("orders", "order_items", "order_payments", "order_reviews")


@dataclass(frozen=True)
class Position:
    cycle: int
    batch: int

    @property
    def as_of(self) -> dt.date:
        return as_of(self.batch)


def as_of(batch: int) -> dt.date:
    """The simulated date a batch is known at: events strictly before it are in."""
    if not 0 <= batch < BATCHES:
        raise ValueError(f"batch {batch} is outside 0..{BATCHES - 1}")
    return START + dt.timedelta(days=batch)


def position(today: dt.date) -> Position:
    """Which cycle and batch the warehouse should have loaded on a real calendar day."""
    days = (today - ANCHOR).days
    if days < 0:
        return Position(0, 0)
    return Position(days // BATCHES, days % BATCHES)


def _ts(value: str) -> dt.datetime | None:
    return dt.datetime.fromisoformat(value) if value else None


def _before(value: str, cutoff: dt.datetime) -> bool:
    ts = _ts(value)
    return ts is not None and ts < cutoff


def order_as_of(row: dict[str, str], day: dt.date) -> dict[str, str] | None:
    """The order as the business knew it at the start of `day`; None if not bought yet.

    Event times that had not happened yet are blank. The status follows the latest event that
    had happened. Once every recorded event has happened the row is the source row unchanged,
    which keeps statuses with no event behind them (canceled, unavailable, invoiced...).
    """
    cutoff = dt.datetime.combine(day, dt.time())
    if not _before(row["order_purchase_timestamp"], cutoff):
        return None
    events = [_ts(row[c]) for c, _ in ORDER_EVENTS]
    if all(ts is None or ts < cutoff for ts in events):
        return dict(row)
    out = dict(row)
    status, latest = "created", None
    for (column, event_status), ts in zip(ORDER_EVENTS, events, strict=True):
        if ts is None or ts >= cutoff:
            out[column] = ""
        elif latest is None or ts >= latest:
            status, latest = event_status, ts
    out["order_status"] = status
    return out


def review_as_of(row: dict[str, str], day: dt.date) -> dict[str, str] | None:
    """The review at the start of `day`; None if not written yet. The answer time stays blank
    until the answer happened."""
    cutoff = dt.datetime.combine(day, dt.time())
    if not _before(row["review_creation_date"], cutoff):
        return None
    out = dict(row)
    if not _before(row["review_answer_timestamp"], cutoff):
        out["review_answer_timestamp"] = ""
    return out


def _event_days(values: list[str]) -> set[dt.date]:
    return {ts.date() for ts in map(_ts, values) if ts is not None}


class Snapshot:
    """The four changing source files, indexed by the day each row's events happened."""

    def __init__(self, data_dir: Path, files: dict[str, str]):
        self.rows = {name: _read(data_dir / files[name]) for name in CHANGE_TABLES}
        self.orders_by_id = {r["order_id"]: r for r in self.rows["orders"]}
        self.order_days: dict[dt.date, list[dict]] = defaultdict(list)
        self.purchase_day: dict[str, dt.date] = {}
        for r in self.rows["orders"]:
            for d in _event_days([r["order_purchase_timestamp"]] + [r[c] for c, _ in ORDER_EVENTS]):
                self.order_days[d].append(r)
            self.purchase_day[r["order_id"]] = _ts(r["order_purchase_timestamp"]).date()
        self.review_days: dict[dt.date, list[dict]] = defaultdict(list)
        for r in self.rows["order_reviews"]:
            for d in _event_days([r["review_creation_date"], r["review_answer_timestamp"]]):
                self.review_days[d].append(r)

    def batch(self, b: int) -> dict[str, list[dict[str, str]]]:
        """Rows of batch b for each change table, without the batch metadata columns."""
        known_at = as_of(b)
        if b == 0:
            orders = [o for o in (order_as_of(r, known_at) for r in self.rows["orders"]) if o]
            reviews = [v for v in (review_as_of(r, known_at) for r in self.rows["order_reviews"]) if v]
            new_ids = {o["order_id"] for o in orders}
        else:
            day = known_at - dt.timedelta(days=1)
            # A few source rows record an event before the purchase; such a day yields no row yet.
            changed_orders = _unique(self.order_days.get(day, []), "order_id")
            changed_reviews = _unique(self.review_days.get(day, []), "review_id", "order_id")
            orders = [o for o in (order_as_of(r, known_at) for r in changed_orders) if o]
            reviews = [v for v in (review_as_of(r, known_at) for r in changed_reviews) if v]
            new_ids = {i for i, d in self.purchase_day.items() if d == day}
        return {
            "orders": orders,
            "order_items": [r for r in self.rows["order_items"] if r["order_id"] in new_ids],
            "order_payments": [r for r in self.rows["order_payments"] if r["order_id"] in new_ids],
            "order_reviews": reviews,
        }


def _unique(rows: list[dict], *key: str) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        k = tuple(r[c] for c in key)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
