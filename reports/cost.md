# Cost report (2026-11-25)

Prices: on-demand list price of $6.25/TiB. The project runs in the BigQuery sandbox,
so it is billed nothing; the dollars are what the same work would cost on demand.

## Build (latest prod dbt run)

74 queries processed 162.29 MB and would bill 630.00 MB ($0.0038 per build).

| dbt node | Queries | Processed | Billed |
|---|---|---|---|
| fct_orders | 3 | 40.08 MB | 50.00 MB |
| fct_order_items | 3 | 21.32 MB | 50.00 MB |
| dim_customers | 3 | 8.66 MB | 10.00 MB |
| mart_monthly_kpis | 3 | 7.39 MB | 10.00 MB |
| source_relationships_raw_order_items_order_id__order_id__source | 1 | 6.88 MB | 20.00 MB |
| relationships_fct_orders_customer_id__customer_id__ref_dim_cust | 1 | 6.45 MB | 20.00 MB |
| assert_amounts_not_negative | 1 | 5.29 MB | 10.00 MB |
| assert_money_reconciles | 1 | 4.84 MB | 20.00 MB |
| source_not_null_raw_order_items_order_id | 1 | 3.65 MB | 10.00 MB |
| source_not_null_raw_order_payments_order_id | 1 | 3.37 MB | 10.00 MB |
| 48 other models and tests | 56 | 54.36 MB | 420.00 MB |

## Analyst queries: partitioned and clustered vs. unpartitioned

| Question | fct_orders (partitioned) | Unpartitioned copy | Bytes saved |
|---|---|---|---|
| GMV and orders in one month | 0.17 MB | 2.28 MB | 92% |
| Late rate in one state over a quarter | 0.48 MB | 2.27 MB | 79% |
| Orders by state for a year | 0.52 MB | 1.14 MB | 55% |
| Monthly late rate over the whole history (no filter: nothing to prune) | 0.85 MB | 0.85 MB | 0% |

Billing rounds every query up to at least 10 MB, so on a table this small the bill is the same either
way; the bytes read are what scale with data volume.

## Storage

| Dataset | Tables | Logical bytes |
|---|---|---|
| marts | 8 | 52.87 MB |
| ops | 2 | 0.00 MB |
| raw | 8 | 58.91 MB |
| staging | 7 | 0.00 MB |

Total 111.79 MB, 1.1% of the sandbox's 10 GiB lifetime allowance.
