# 0001: BigQuery in sandbox mode, designed around its limits

## Context

The project has to cost nothing and need no credit card. BigQuery's sandbox gives 1 TiB of
queries a month and 10 GiB of storage for the life of the project, with no billing account. In
exchange it has hard limits: no DML (`INSERT`, `UPDATE`, `MERGE`, `DELETE`), no streaming, no
Cloud Storage or Cloud KMS, every table and partition expires after 60 days, and the 10 GiB of
storage is not restored when data is deleted.

## Decision

Use the sandbox, and make each limit a design input instead of a surprise:

| Limit | Design |
|---|---|
| No DML | Raw data arrives through load jobs (free and allowed); dbt builds every mart with `CREATE OR REPLACE TABLE ... AS SELECT`; audit and cost rows are appended with load jobs too. No incremental `MERGE` models. |
| 60-day expiration | The deploy runs weekly. dbt recreates its tables and views; the loader and the cost report push the expiration of raw and ops tables forward with a metadata update, not a rewrite. |
| Partitions older than 60 days expire | Integer-range partitions on a YYYYMM key instead of date partitions (ADR 0004). |
| 10 GiB lifetime storage | Raw tables are reloaded only when the source file's SHA-256 changes. The 59 MB geolocation file, which no model uses, is not loaded. The cost report tracks storage against the allowance. |
| No Cloud Storage | Terraform state stays in Cloud Shell (ADR 0005). |
| No Cloud KMS | Data is encrypted with Google-managed keys; the checkov rule for customer-managed keys is skipped with this reason written next to the resource. |

## Consequences

The same code runs unchanged on a billed project, where most of these workarounds simply stop
mattering (incremental models and a Cloud Storage backend would then be the next steps). The
datasets live in `southamerica-east1`, so Brazilian customer data stays in Brazil.
