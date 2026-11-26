{{
  config(
    materialized="incremental",
    incremental_strategy="insert_overwrite",
    partition_by={
      "field": "purchase_month_key",
      "data_type": "int64",
      "range": {"start": 201601, "end": 201901, "interval": 1},
      "copy_partitions": true
    },
    cluster_by=["customer_state", "status"],
    on_schema_change="fail"
  )
}}
-- Integer-range partitions by purchase month (202208-style key), not date partitions: in the
-- sandbox every date partition older than 60 days expires, which would delete all of 2016-2018
-- on creation (docs/adr/0004).
--
-- Incremental (docs/adr/0006): each run rebuilds only the purchase months that hold an order
-- with a new version, item, payment or review since the last run, and swaps those partitions in
-- with copy jobs, because the sandbox allows no MERGE. A change to an order bought months ago
-- (delivered today, reviewed today) rebuilds that order's month. source_batch is the latest
-- replay batch behind each row; its maximum is the watermark.

{% if is_incremental() %}
with watermark as (
    select coalesce(max(source_batch), -1) as batch from {{ this }}
),

changed_orders as (
    select order_id from {{ ref('stg_orders') }} where source_batch > (select batch from watermark)
    union distinct
    select order_id from {{ ref('stg_order_items') }} where source_batch > (select batch from watermark)
    union distinct
    select order_id from {{ ref('stg_order_payments') }} where source_batch > (select batch from watermark)
    union distinct
    select order_id from {{ ref('stg_order_reviews') }} where source_batch > (select batch from watermark)
),

changed_months as (
    select distinct extract(year from purchased_at) * 100 + extract(month from purchased_at) as purchase_month_key
    from {{ ref('stg_orders') }}
    where order_id in (select order_id from changed_orders)
),

{% else %}
with
{% endif %}
reviews as (
    select order_id, review_score, max(source_batch) over (partition by order_id) as source_batch
    from {{ ref('stg_order_reviews') }}
    -- latest review per order; ties broken by answer time and id, so rebuilds are identical
    qualify row_number() over (
        partition by order_id order by reviewed_at desc, answered_at desc, review_id
    ) = 1
),

payments as (
    select
        order_id,
        sum(payment_value) as total_payment_value,
        max(payment_installments) as max_installments,
        array_agg(payment_type order by payment_value desc, payment_sequential limit 1)[offset(0)] as main_payment_type,
        max(source_batch) as source_batch
    from {{ ref('stg_order_payments') }}
    group by order_id
),

items as (
    select
        order_id,
        count(*) as item_count,
        sum(price) as total_item_price,
        sum(freight_value) as total_freight,
        max(source_batch) as source_batch
    from {{ ref('stg_order_items') }}
    group by order_id
)

select
    o.order_id,
    o.customer_id,
    c.customer_unique_id,
    c.customer_state,
    o.status,
    date(o.purchased_at) as purchase_date,
    extract(year from o.purchased_at) * 100 + extract(month from o.purchased_at) as purchase_month_key,
    p.total_payment_value,
    p.max_installments,
    p.main_payment_type,
    coalesce(i.item_count, 0) as item_count,
    i.total_item_price,
    i.total_freight,
    r.review_score,
    date_diff(date(o.delivered_to_customer_at), date(o.purchased_at), day) as delivery_days,
    date_diff(date(o.delivered_to_customer_at), o.estimated_delivery_date, day) as delay_days,
    -- late = delivered on a later calendar day than promised; the promise is a date, so a
    -- timestamp comparison would flag every delivery made on the promised day
    coalesce(date(o.delivered_to_customer_at) > o.estimated_delivery_date, false) as is_delayed,
    greatest(
        o.source_batch, coalesce(r.source_batch, -1), coalesce(p.source_batch, -1), coalesce(i.source_batch, -1)
    ) as source_batch
from {{ ref('stg_orders') }} as o
left join {{ ref('stg_customers') }} as c using (customer_id)
left join reviews as r using (order_id)
left join payments as p using (order_id)
left join items as i using (order_id)
{% if is_incremental() %}
where extract(year from o.purchased_at) * 100 + extract(month from o.purchased_at)
    in (select purchase_month_key from changed_months)
{% endif %}
