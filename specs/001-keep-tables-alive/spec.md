# Spec 001: keep every table alive in the sandbox

## Problem
Deploy 46074073085 (2026-11-27) failed: BigQuery refused to push `raw.customers`'s expiration
to now + 59 days ("Table expiration time must be less than 60 days while in sandbox mode"),
although the same update succeeded two hours earlier. The loader also extended only the raw
and ops datasets, while dbt's incremental models are never recreated and expire as well.

## Requirements
- R1. Every table in every dataset of the project is kept alive; views are skipped (dbt
  recreates them each run).
- R2. A table whose expiration is more than 30 days away is left alone (no metadata update).
- R3. When an extension is refused, the table is renewed by copy (new creation time), never
  leaving the data in no table at any step.
- R4. Description and labels survive a renewal.
