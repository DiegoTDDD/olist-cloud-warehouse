-- After a build, no order version, item, payment or review is newer than what the fact table
-- has processed: the incremental run did not leave a change behind.
with watermark as (
    select max(source_batch) as batch from {{ ref('fct_orders') }}
),

loaded as (
    select max(source_batch) as batch from {{ ref('stg_orders') }}
)

select w.batch as fact_watermark, l.batch as latest_order_batch
from watermark as w cross join loaded as l
where w.batch < l.batch
