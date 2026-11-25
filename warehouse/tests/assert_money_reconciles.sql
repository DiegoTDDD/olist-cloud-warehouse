-- Item revenue in the fact table matches the raw items to the cent, overall and per month:
-- a join that drops or duplicates items shows up here before it shows up in a dashboard.
with fact as (
    select purchase_month_key, sum(total_item_price) as revenue
    from {{ ref('fct_orders') }}
    group by 1
),
items as (
    select purchase_month_key, sum(price) as revenue
    from {{ ref('fct_order_items') }}
    group by 1
)
select f.purchase_month_key, f.revenue as fact_revenue, i.revenue as items_revenue
from fact as f
full outer join items as i using (purchase_month_key)
where coalesce(f.revenue, 0) != coalesce(i.revenue, 0)
