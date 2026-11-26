# 0006: Daily change feed and incremental marts without DML

## Context

The Olist files are a finished snapshot. Loading them whole and rebuilding every table tests
none of what makes a warehouse hard in production: data that arrives every day, records that
change after they first arrive (an order is bought, then shipped, then delivered, then
reviewed weeks later), runs that fail and must catch up, and marts that should not be rebuilt
from scratch every day. The sandbox also rules out the usual tools for this: no `MERGE`, no
streaming, no scheduled queries (ADR 0001).

## Decision

**A replay turns the snapshot into a daily change feed** (`pipeline/replay.py`). Batch 0 is the
business as known on 2018-01-01; batch *b* holds every order and review that had an event on
day *b* of 2018, as known at the end of that day. Events that had not happened yet are blank,
and the status follows the latest event. One real day is one batch, starting 2026-11-26; after
2018-10-30 the replay starts a new cycle. A unit test replays all 303 batches and checks that
the latest row per key equals the source files exactly.

**Raw keeps every version.** The four change tables are integer-range partitioned on `_batch`.
Each batch is a load job into `table$<batch>` with `WRITE_TRUNCATE`, which replaces that one
partition: rerunning a day, or catching up after an outage, gives the same table. Each row
carries `_batch`, `_as_of` (simulated date) and `_loaded_at` (real time). The staging views keep
the latest version per key.

**The fact tables are incremental with `insert_overwrite` and `copy_partitions`.** Each row of
`fct_orders` records the newest batch behind it (`source_batch`); the table's maximum is the
watermark. A run finds every order with a version, item, payment or review newer than the
watermark, rebuilds the whole purchase month of each one into a temporary table, and dbt
replaces those month partitions with copy jobs, which the sandbox allows. A delivery today of
an order bought in November rebuilds November. Dimensions and the small aggregate marts are
rebuilt in full; they cost less than tracking their changes.

**Correctness is tested, not assumed.** Every pull request replays 31 days into its own
datasets, builds, builds again incrementally, rebuilds everything from scratch, and fails
unless the two hold the same rows (`scripts/compare_builds.py` compares a row-level hash of
every mart). A dbt test checks that no loaded change is newer than the fact table's watermark.

**Freshness and alerts.** The loader writes one audit row per change table per run.
`dbt source freshness` on those rows warns after 26 hours and errors after 50; it runs after
every deploy and every six hours on its own. A failed deploy or a freshness error opens a
GitHub issue labelled `pipeline-alert`, and the next good run closes it.

## Consequences

A normal day rebuilds a handful of month partitions instead of the whole history, and the
same code handles first load, daily load, catch-up and a full reset. A new cycle, a changed
source file or a change of table layout resets the change tables and triggers a full refresh.

The replay is a simulation: the timing comes from the events recorded in the data, but some
statuses (canceled, unavailable, invoiced) have no timestamp, so they appear when the order's
last recorded event happens. A few source rows record an event before the purchase or a review
before the order; they arrive on the day that makes them consistent, which is the same
late-arriving-data case a real feed has.

The numbers in the decision report move with the replay. They are stamped with their as-of date.
