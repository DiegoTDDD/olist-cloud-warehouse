# Runbook

What to do when the pipeline alerts. Every alert is a GitHub issue labelled `pipeline-alert`
with a link to the failed run; the next successful deploy closes it.

## The daily deploy failed

Open the run from the issue and find the first red step.

| Step | Usual cause | Fix |
|---|---|---|
| Download / SHA-256 | the mirror changed or is down | The hashes protect the data: do not edit them. Wait and rerun, or put the Kaggle files in `data/raw/`. |
| Load raw | BigQuery quota or a transient API error | Rerun the workflow. Loads are idempotent: each batch replaces its own partition, and the loader resumes from the last batch it recorded. |
| dbt build, a model | SQL or contract error after a merge | Revert or fix on a branch; the pull request build reproduces it in its own datasets. |
| dbt build, a test | the data broke a rule | Read the failing rows (`dbt test --select <test> --store-failures` on a branch). Do not delete the test to get green. |
| Freshness | today's batch did not arrive | See below. |

Rerun: Actions > deploy > Run workflow.

## Data is late (freshness error)

`dbt source freshness` errors when no batch has loaded for 50 hours. Check the deploy history:
if the schedule did not run (GitHub disables schedules on repositories with no activity for
60 days), re-enable it and run the deploy by hand. The loader loads every batch that is due, so
one run catches up on all missed days.

## A model must be rebuilt from scratch

Actions > deploy > Run workflow with **full_refresh** ticked. It rebuilds every incremental
model from raw. Needed after changing the logic of an incremental model in a way that alters
past rows (the pull request build compares incremental and full builds, so it will show this).

## Reset the replay

Bumping `LAYOUT` in `pipeline/load_raw.py` makes the next deploy recreate the change tables
from batch 0 up to today and run a full refresh. The same happens by itself at the start of
each replay cycle and when a source file's hash changes.

## Check what was loaded

```sql
select table_name, batch_from, batch_to, rows, loaded_at
from ops.load_audit
where action = 'replay'
order by loaded_at desc
limit 20
```
