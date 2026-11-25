# 0003: Explicit schemas for raw, enforced contracts for marts

## Context

Schema auto-detection guesses: a column of zip codes becomes an integer and loses its leading
zero, a column that is empty in the first rows becomes a string. A wrong type found in a
dashboard months later is expensive.

## Decision

- **Raw:** every file has an explicit schema in `pipeline/contracts.py`. A file that does not
  match fails the load (`max_bad_records=0`), and the loaded row count must equal the number
  of CSV records (counted as records, since review comments contain line breaks). Zip codes
  are strings. Times are `DATETIME`, not `TIMESTAMP`: Olist records Brazilian local time
  without a zone, and storing it as UTC would shift every hour.
- **Marts:** dbt model contracts are enforced. dbt creates each table with the declared columns
  and types and fails the build if the SQL produces anything else; `not null` is enforced by
  BigQuery itself. Primary keys are declared (BigQuery uses them in planning) and tested.

## Consequences

A change in the source or a careless edit to a model fails CI instead of reaching an analyst.
The cost is writing the types down once, which is also the documentation.
