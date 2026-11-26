# Olist cloud warehouse

[![deploy](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/deploy.yml/badge.svg)](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/deploy.yml)
[![ci](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/DiegoTDDD/olist-cloud-warehouse/actions/workflows/ci.yml)

**Project page: [diegotddd.github.io/olist-cloud-warehouse](https://diegotddd.github.io/olist-cloud-warehouse/)**
(the decision, the cost and the architecture, rebuilt after every deploy) and the
[dbt docs](https://diegotddd.github.io/olist-cloud-warehouse/dbt/) (every model, column and its lineage).

A data warehouse for the Olist marketplace (99,441 orders, Brazil, 2016 to 2018) running in
Google BigQuery, built so that it costs nothing and could still be handed to a production
team: infrastructure as code, keyless CI, contracts on every table, tests on every build,
and measured cost.

| | |
|---|---|
| Cloud | Google Cloud, BigQuery in `southamerica-east1` (customer data stays in Brazil) |
| Infrastructure | Terraform: 4 datasets, 2 service accounts, Workload Identity Federation, IAM per layer |
| CI identity | No keys: GitHub's OIDC token is exchanged for a one-hour Google token |
| Transformation | dbt: 15 models, enforced contracts, 43 data tests |
| Data quality | Raw schemas declared, file hashes checked, row counts reconciled, money reconciled to the cent |
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
     ├─ deploy (main, weekly) ─ olist-deployer ──────► │ raw ──► staging (views) ──► marts (tables) ─► ops │
     │                                                 └────────────────────────────────────────────────┘
     └─ pull request ───────── olist-pr-builder ─────► ci_pr_<n>_staging, ci_pr_<n>_marts (dropped after)
```

| Layer | What | Who writes | Who reads |
|---|---|---|---|
| `raw` | The CSV files, explicit schemas, one table each | deployer (load jobs) | deployer, pr-builder |
| `staging` | dbt views: renames, casts, category translation | deployer | deployer |
| `marts` | Star schema and decision marts, contracts enforced | deployer | analysts (`analyst_members`) |
| `ops` | Load audit and cost ledger | deployer | deployer |

## How a change ships

1. **Every push and pull request** (`ci.yml`, no cloud access): ruff, unit tests, `dbt parse`,
   `terraform fmt` and `validate`, and a checkov security scan of the Terraform.
2. **Every pull request** (`pr.yml`): the pr-builder account builds and tests the whole
   warehouse in BigQuery, in datasets of its own, and drops them at the end. It can read raw
   and cannot write any production dataset.
3. **Merge to main, and every Monday** (`deploy.yml`): the deployer loads raw (only files
   whose SHA-256 changed), runs `dbt build`, generates the dbt docs, and commits the cost and
   decision reports. The weekly run also keeps the sandbox's 60-day expiration from deleting
   anything.

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

## Run it on your own project

1. Create a Google Cloud project (the BigQuery sandbox needs no card) and open this
   repository in Cloud Shell. Change `github_repository` and the two ids in
   `infra/variables.tf` to your fork's.
2. `bash bootstrap`: installs a pinned, checksummed Terraform, applies `infra/`, and prints
   four values.
3. Store them as repository variables (`GCP_PROJECT`, `WIF_PROVIDER`, `DEPLOYER_SA`,
   `PR_BUILDER_SA`) and run the deploy workflow.

Locally: `pip install -r requirements.txt -r requirements-dev.txt && pytest`; with gcloud
credentials, `python -m pipeline.load_raw --project <id>` and `cd warehouse && dbt build`.

## Limits

- The sandbox rules out incremental `MERGE` models, Cloud Storage and customer-managed keys
  (ADR 0001); on a billed project those are the next steps.
- Terraform is applied by hand from Cloud Shell, not by CI (ADR 0005).
- The data is a fixed 2016-2018 snapshot, so there is no freshness monitoring to show.
- The decision mart is correlation in observational data: late orders may differ in other ways.

## Data

[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce),
CC BY-NC-SA 4.0. The same data feeds [olist-analytics](https://github.com/DiegoTDDD/olist-analytics)
(dbt on DuckDB) and [olist-ai-analyst](https://github.com/DiegoTDDD/olist-ai-analyst).
