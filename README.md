# Olist cloud warehouse

[![deploy](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/deploy.yml/badge.svg)](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/deploy.yml)
[![ci](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/ci.yml)

**Project page: [diegotddd.github.io/olist-cloud-warehouse](https://diegotddd.github.io/olist-cloud-warehouse/)**
(the decision, the cost and the architecture, rebuilt after every deploy) and the
[dbt docs](https://diegotddd.github.io/olist-cloud-warehouse/dbt/) (every model, column and its lineage).

A data warehouse for the Olist marketplace (99,441 orders, Brazil, 2016 to 2018) running in
Google BigQuery, built so that it costs nothing and could still be handed to a production
team. Data arrives every day as a change feed: orders are bought, shipped, delivered and
reviewed on different days, and the marts update incrementally. Every pull request proves
the incremental build equals a full rebuild, a late or failed run opens an alert, and there
is a runbook. Infrastructure as code, keyless CI, contracts on every table, measured cost.

| | |
|---|---|
| Cloud | Google Cloud, BigQuery in `southamerica-east1` (customer data stays in Brazil) |
| Infrastructure | Terraform: 4 datasets, 2 service accounts, Workload Identity Federation, IAM per layer |
| CI identity | No keys: GitHub's OIDC token is exchanged for a one-hour Google token |
| Data arrival | Daily change feed: the 2016-2018 history replayed one day per real day, every version of an order kept (ADR 0006) |
| Transformation | dbt: 15 models, enforced contracts, 45 data tests; fact tables incremental, rebuilding only the months that changed |
| Operations | Daily schedule with catch-up, freshness checked every 6 hours, failures open a GitHub issue, [runbook](docs/runbook.md) |
| Data quality | Raw schemas declared, file hashes checked, rows per batch reconciled, money reconciled to the cent, incremental = full rebuild on every PR |
| Cost | Every query labelled; build and query bytes measured each deploy; 1 GB per-query guardrail |
| Price | US$ 0: BigQuery sandbox, GitHub Actions |

**Measured on the latest deploy** ([reports/cost.md](reports/cost.md)):

| | |
|---|---|
| Full build, all models and tests | 162 MB read, US$ 0.004 at on-demand list price |
| "GMV in one month" on the partitioned fact table | 92% fewer bytes than an unpartitioned copy |
| "Late rate in one state over a quarter" | 79% fewer bytes |
| Storage used | 112 MB, 1.1% of the sandbox's 10 GiB lifetime allowance |

## The decision it supports

[reports/decision.md](reports/decision.md), rebuilt on every deploy from `mart_delivery_satisfaction`:
6.8% of delivered orders arrive late. Every day of delay costs rating until about six days
late (4.03 on the promised day, 3.73 after one day, 1.81 after six; the 1-star share goes from
8.5% to 68.5%). After that the rating stays near 1.7. Logistics money pays off inside the
first week of a delay: turning a 3-day delay into a 1-day one recovers rating, turning a
20-day delay into a 12-day one recovers almost none.

## Architecture

```
GitHub Actions ──OIDC token──► Workload Identity Federation ──► service account (1-hour token)
     │                          accepts only this repository,        │
     │                          main branch or pull requests          ▼
     │                                                 ┌──────────── BigQuery (São Paulo) ─────────────┐
     ├─ deploy (daily, main) ── olist-deployer ──────► │ raw ──► staging (views) ──► marts (tables) ─► ops │
     │                                                 └────────────────────────────────────────────────┘
     └─ pull request ───────── olist-pr-builder ─────► ci_pr_<n>_staging, ci_pr_<n>_marts (dropped after)
```

| Layer | What | Who writes | Who reads |
|---|---|---|---|
| `raw` | Explicit schemas. Orders, items, payments and reviews as change feeds, one partition per daily batch; reference tables whole | deployer (load jobs) | deployer, pr-builder |
| `staging` | dbt views: latest version of each record, renames, casts, category translation | deployer | deployer |
| `marts` | Star schema and decision marts, contracts enforced; incremental fact tables | deployer | analysts (`analyst_members`) |
| `ops` | Load audit and cost ledger | deployer | deployer |

## How data arrives

The Olist files are a finished snapshot, so `pipeline/replay.py` turns them into what a
production warehouse actually receives: a daily feed of changes. Batch 0 is the business as
known on 2018-01-01. Each real day since 2026-11-26 loads the next day of 2018: the orders
bought that day, and a new version of every older order that was approved, shipped or
delivered that day, plus the reviews written or answered. Times that had not happened yet are
blank; the status follows the latest event. A unit test replays all 303 batches and checks
that the latest version of every record equals the source files exactly.

- **Idempotent and self-healing.** Each batch is a load job that replaces its own partition
  (`raw.orders$<batch>`), so a rerun changes nothing, and a run after an outage loads every
  missed day in order.
- **Incremental marts without MERGE.** The sandbox has no DML, so `fct_orders` and
  `fct_order_items` use dbt's `insert_overwrite` with `copy_partitions`: every purchase month
  holding an order with a newer version, item, payment or review than the table's watermark is
  rebuilt and swapped in with a copy job. A delivery today of an order bought in November
  rebuilds November and nothing else.
- **Proven on every pull request.** The PR build replays 31 days, builds, builds again
  incrementally, rebuilds from scratch into separate datasets, and fails unless every mart
  holds the same rows in both (`scripts/compare_builds.py`).
- **Watched.** `dbt source freshness` warns when no batch has landed for 26 hours and errors at
  50, after every deploy and every six hours on its own (`monitor.yml`). A failure opens a
  GitHub issue labelled `pipeline-alert`; the next good run closes it.
  [docs/runbook.md](docs/runbook.md) says what to do for each failure.

## How a change ships

1. **Every push and pull request** (`ci.yml`, no cloud access): ruff, unit tests (including
   the full replay), `dbt parse`, `terraform fmt` and `validate`, and a checkov security scan.
2. **Every pull request** (`pr.yml`): the pr-builder account replays 31 days into datasets of
   its own, builds incrementally and from scratch, compares them, and drops everything at the
   end. It cannot write any production dataset.
3. **Every day at 06:17 São Paulo time, and on merge to main** (`deploy.yml`): the deployer
   loads every batch due, runs `dbt build` (incremental; a full refresh after a reset or on
   request), checks freshness, generates the dbt docs, and commits the cost and decision
   reports.

## What went wrong, and what changed

- **Keyless auth was rejected on the first deploy:** "rejected by the attribute condition".
  GitHub now writes the owner and repository into the OIDC subject with their numeric ids
  (`repo:DiegoTDDD@183739024/olist-cloud-warehouse@1472254812:ref:refs/heads/main`). A
  throwaway workflow printed the token's claims, never the token, and the trust was
  rewritten to match. Pinning ids is stronger than pinning names: a re-created repository
  with the same name gets a new id.
- **Least privilege bit the cost report twice.** Reading job history needs
  `bigquery.jobs.list`, which `jobUser` lacks and `bigquery.user` grants along with dataset
  creation, so a one-permission custom role grants exactly that. Then
  `INFORMATION_SCHEMA.TABLE_STORAGE` turned out not to be enabled for a new project, so table
  sizes come from each dataset's `__TABLES__`.
- **The first cost report counted three deploys and the docs catalog** (9 queries per model).
  Every dbt command now labels its queries with its invocation id, and the report reads one
  build.
- **The first decision text said most of the damage happens on day one.** The measured buckets
  say otherwise: the rating keeps falling for six days. The text is now computed from the data.

## Decisions

- [0001 BigQuery in sandbox mode, designed around its limits](docs/adr/0001-bigquery-sandbox.md)
- [0002 CI authenticates without keys, as two least-privilege identities](docs/adr/0002-keyless-ci.md)
- [0003 Explicit schemas for raw, enforced contracts for marts](docs/adr/0003-raw-contracts.md)
- [0004 Integer-range partitions by month, clustered by state and status](docs/adr/0004-partitioning.md)
- [0005 Terraform state stays with the one person who applies it](docs/adr/0005-terraform-state.md)
- [0006 Daily change feed and incremental marts without DML](docs/adr/0006-daily-replay-and-incremental-models.md)

## Run it on your own project

1. Create a Google Cloud project (the BigQuery sandbox needs no card) and open this
   repository in Cloud Shell. Change `github_repository` and the two ids in
   `infra/variables.tf` to your fork's.
2. `bash bootstrap`: installs a pinned, checksummed Terraform, applies `infra/`, and prints
   four values.
3. Store them as repository variables (`GCP_PROJECT`, `WIF_PROVIDER`, `DEPLOYER_SA`,
   `PR_BUILDER_SA`) and run the deploy workflow.

Locally: `bash scripts/download_data.sh && pip install -r requirements.txt -r requirements-dev.txt && pytest`;
with gcloud credentials, `python -m pipeline.load_raw --project <id>` and `cd warehouse && dbt build`.

## Limits

- The change feed is a replay of real events, not a live system. Statuses with no timestamp in
  the source (canceled, unavailable) appear when the order's last recorded event happens.
- The data is small (about 100,000 orders): the design choices are the ones that matter at
  scale, but this project does not show tables of terabytes.
- The sandbox rules out Cloud Storage and customer-managed keys (ADR 0001); Terraform is
  applied by hand from Cloud Shell, not by CI (ADR 0005).
- The decision mart is correlation in observational data: late orders may differ in other ways.

## Data

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
CC BY-NC-SA 4.0. The same data feeds [olist-analytics](https://github.com/DiegoTDDD/olist-analytics)
(dbt on DuckDB) and [olist-ai-analyst](https://github.com/DiegoTDDD/olist-ai-analyst).
