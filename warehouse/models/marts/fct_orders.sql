{{
  config(
    partition_by={
      "field": "purchase_month_key",
      "data_type": "int64",
      "range": {"start": 201601, "end": 201901, "interval": 1}
    },
    cluster_by=["customer_state", "status"]
  )
}}
-- Integer-range partitions by purchase month (202208-style key), not date partitions: in the
-- sandbox every date partition older than 60 days expires, which would delete all of 2016-2018
-- on creation (docs/adr/0004).

with reviews as (
    select order_id, review_score
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
        array_agg(payment_type order by payment_value desc, payment_sequential limit 1)[offset(0)] as main_payment_type
    from {{ ref('stg_order_payments') }}
    group by order_id
),

items as (
    select
        order_id,
        count(*) as item_count,
        sum(price) as total_item_price,
        sum(freight_value) as total_freight
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
    coalesce(date(o.delivered_to_customer_at) > o.estimated_delivery_date, false) as is_delayed
from {{ ref('stg_orders') }} as o
left join {{ ref('stg_customers') }} as c using (customer_id)
left join reviews as r using (order_id)
left join payments as p using (order_id)
left join items as i using (order_id)
