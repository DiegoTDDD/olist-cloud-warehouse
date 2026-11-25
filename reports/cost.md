# Cost report (2026-11-25)

Prices: on-demand list price of $6.25/TiB. The project runs in the BigQuery sandbox,
so it is billed nothing; the dollars are what the same work would cost on demand.

## Build (latest prod dbt run)

231 queries processed 846.87 MB and would bill 2,340.00 MB ($0.0139 per build).

| dbt node | Queries | Processed | Billed |
|---|---|---|---|
| None | 9 | 360.00 MB | 450.00 MB |
| fct_orders | 9 | 120.23 MB | 150.00 MB |
| fct_order_items | 9 | 63.97 MB | 150.00 MB |
| dim_customers | 9 | 25.99 MB | 30.00 MB |
| mart_monthly_kpis | 9 | 22.17 MB | 30.00 MB |
| source_relationships_raw_order_items_order_id__order_id__source | 3 | 20.63 MB | 60.00 MB |
| relationships_fct_orders_customer_id__customer_id__ref_dim_cust | 3 | 19.35 MB | 60.00 MB |
| assert_amounts_not_negative | 3 | 15.86 MB | 30.00 MB |
| assert_money_reconciles | 3 | 14.53 MB | 60.00 MB |
| source_not_null_raw_order_items_order_id | 3 | 10.96 MB | 30.00 MB |
| source_not_null_raw_order_payments_order_id | 3 | 10.11 MB | 30.00 MB |
| source_not_null_raw_customers_customer_id | 3 | 9.67 MB | 30.00 MB |
| source_not_null_raw_orders_customer_id | 3 | 9.67 MB | 30.00 MB |
| source_not_null_raw_orders_order_id | 3 | 9.67 MB | 30.00 MB |
| source_unique_raw_orders_order_id | 3 | 9.67 MB | 30.00 MB |
| not_null_stg_customers_customer_id | 3 | 9.67 MB | 30.00 MB |
| unique_stg_customers_customer_id | 3 | 9.67 MB | 30.00 MB |
| not_null_stg_orders_order_id | 3 | 9.67 MB | 30.00 MB |
| unique_stg_orders_order_id | 3 | 9.67 MB | 30.00 MB |
| unique_dim_customers_customer_id | 3 | 9.67 MB | 30.00 MB |
| source_unique_raw_customers_customer_id | 3 | 9.67 MB | 30.00 MB |
| unique_fct_orders_order_id | 3 | 9.67 MB | 30.00 MB |
| dim_products | 9 | 8.54 MB | 60.00 MB |
| mart_delivery_satisfaction | 9 | 7.59 MB | 30.00 MB |
| assert_delivered_orders_have_a_delivery_date | 3 | 5.33 MB | 30.00 MB |
| not_null_stg_products_product_id | 3 | 4.78 MB | 60.00 MB |
| unique_stg_products_product_id | 3 | 4.78 MB | 60.00 MB |
| source_not_null_raw_products_product_id | 3 | 3.21 MB | 30.00 MB |
| source_unique_raw_products_product_id | 3 | 3.21 MB | 30.00 MB |
| unique_dim_products_product_id | 3 | 3.21 MB | 30.00 MB |
| accepted_values_stg_orders_status__delivered__shipped__canceled | 3 | 3.12 MB | 30.00 MB |
| assert_is_delayed_matches_delay_days | 3 | 2.49 MB | 30.00 MB |
| source_accepted_values_raw_order_reviews_review_score__false__1 | 3 | 2.27 MB | 30.00 MB |
| source_not_null_raw_order_reviews_review_score | 3 | 2.27 MB | 30.00 MB |
| accepted_values_fct_orders_review_score__false__1__2__3__4__5 | 3 | 2.26 MB | 30.00 MB |
| not_null_stg_products_category | 3 | 1.58 MB | 60.00 MB |
| dim_sellers | 9 | 0.51 MB | 30.00 MB |
| source_not_null_raw_sellers_seller_id | 3 | 0.30 MB | 30.00 MB |
| source_unique_raw_sellers_seller_id | 3 | 0.30 MB | 30.00 MB |
| not_null_stg_sellers_seller_id | 3 | 0.30 MB | 30.00 MB |
| unique_stg_sellers_seller_id | 3 | 0.30 MB | 30.00 MB |
| unique_dim_sellers_seller_id | 3 | 0.30 MB | 30.00 MB |
| unique_dim_dates_date_day | 3 | 0.03 MB | 30.00 MB |
| source_not_null_raw_product_category_name_translation_product_c | 3 | 0.00 MB | 30.00 MB |
| source_unique_raw_product_category_name_translation_product_cat | 3 | 0.00 MB | 30.00 MB |
| unique_mart_monthly_kpis_purchase_month_key | 3 | 0.00 MB | 30.00 MB |
| assert_kpis_cover_every_order | 3 | 0.00 MB | 60.00 MB |
| unique_mart_delivery_satisfaction_delay_bucket_days | 3 | 0.00 MB | 30.00 MB |
| dim_dates | 9 | 0.00 MB | 0.00 MB |
| stg_order_payments | 3 | 0.00 MB | 0.00 MB |
| stg_order_items | 3 | 0.00 MB | 0.00 MB |
| stg_order_reviews | 3 | 0.00 MB | 0.00 MB |
| stg_customers | 3 | 0.00 MB | 0.00 MB |
| stg_products | 3 | 0.00 MB | 0.00 MB |
| stg_orders | 3 | 0.00 MB | 0.00 MB |
| stg_sellers | 3 | 0.00 MB | 0.00 MB |
| assert_delivery_after_purchase | 3 | 0.00 MB | 0.00 MB |
| assert_partitions_hold_every_month | 3 | 0.00 MB | 0.00 MB |
| assert_one_fact_row_per_order | 3 | 0.00 MB | 0.00 MB |

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
| ops | 1 | 0.00 MB |
| raw | 8 | 58.91 MB |
| staging | 7 | 0.00 MB |

Total 111.78 MB, 1.1% of the sandbox's 10 GiB lifetime allowance.
