-- fct_orders has exactly one row per source order: the review, payment and item joins never
-- duplicate or drop an order. raw.orders holds every version of an order, so count orders.
select fact_rows, source_orders
from (
    select
        (select count(*) from {{ ref('fct_orders') }}) as fact_rows,
        (select count(distinct order_id) from {{ source('raw', 'orders') }}) as source_orders
)
where fact_rows != source_orders
