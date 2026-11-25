-- fct_orders has exactly one row per source order: the review, payment and item joins never
-- duplicate or drop an order.
select fact_rows, source_rows
from (
    select
        (select count(*) from {{ ref('fct_orders') }}) as fact_rows,
        (select count(*) from {{ source('raw', 'orders') }}) as source_rows
)
where fact_rows != source_rows
