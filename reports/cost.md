# Cost report (2026-11-28)

Prices: on-demand list price of $6.25/TiB. The project runs in the BigQuery sandbox,
so it is billed nothing; the dollars are what the same work would cost on demand.

## Build (latest prod dbt run)

80 queries processed 110.67 MB and would bill 680.00 MB ($0.0041 per build).

| dbt node | Queries | Processed | Billed |
|---|---|---|---|
| fct_orders | 5 | 24.24 MB | 70.00 MB |
| fct_order_items | 5 | 11.48 MB | 70.00 MB |
| assert_raw_one_version_per_batch | 1 | 9.74 MB | 40.00 MB |
| dim_customers | 3 | 8.66 MB | 10.00 MB |
| relationships_fct_orders_customer_id__customer_id__ref_dim_cust | 1 | 4.71 MB | 20.00 MB |
| mart_monthly_kpis | 3 | 3.37 MB | 10.00 MB |
| source_not_null_raw_customers_customer_id | 1 | 3.22 MB | 10.00 MB |
| source_unique_raw_customers_customer_id | 1 | 3.22 MB | 10.00 MB |
| not_null_stg_customers_customer_id | 1 | 3.22 MB | 10.00 MB |
| unique_stg_customers_customer_id | 1 | 3.22 MB | 10.00 MB |
| 50 other models and tests | 58 | 35.57 MB | 420.00 MB |

## Analyst queries: partitioned and clustered vs. unpartitioned

| Question | fct_orders (partitioned) | Unpartitioned copy | Bytes saved |
|---|---|---|---|
| GMV and orders in one month | 0.17 MB | 1.05 MB | 83% |
| Late rate in one state over a quarter | 0.01 MB | 1.04 MB | 99% |
| Orders by state for a year | 0.52 MB | 0.52 MB | 1% |
| Monthly late rate over the whole history (no filter: nothing to prune) | 0.39 MB | 0.39 MB | 0% |

Billing rounds every query up to at least 10 MB, so on a table this small the bill is the same either
way; the bytes read are what scale with data volume.

## Storage

| Dataset | Tables | Logical bytes |
|---|---|---|
| marts | 8 | 31.50 MB |
| ops | 2 | 0.02 MB |
| raw | 8 | 37.63 MB |
| staging | 7 | 0.00 MB |

Total 69.15 MB, 0.7% of the sandbox's 10 GiB lifetime allowance.
