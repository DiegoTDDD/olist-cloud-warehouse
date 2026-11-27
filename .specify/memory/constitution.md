# Constitution: olist-cloud-warehouse

1. **Free by design**: BigQuery sandbox and GitHub Actions; every sandbox limit is a design input.
2. **No long-lived keys**: CI authenticates with Workload Identity Federation.
3. **The warehouse never loses data silently**: a step that could delete or expire data fails
   loudly or recovers it.
4. **Numbers come from runs** and are reproducible from the repository.
5. **Every change is tested** (pytest, ruff, dbt tests) before it is pushed.
