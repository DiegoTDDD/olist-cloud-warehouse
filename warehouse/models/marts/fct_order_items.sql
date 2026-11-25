{{
  config(
    partition_by={
      "field": "purchase_month_key",
      "data_type": "int64",
      "range": {"start": 201601, "end": 201901, "interval": 1}
    },
    cluster_by=["category", "seller_state"]
  )
}}

select
    i.order_id,
    i.order_item_id,
    i.product_id,
    p.category,
    i.seller_id,
    s.seller_state,
    o.customer_state,
    o.purchase_month_key,
    i.price,
    i.freight_value
from {{ ref('stg_order_items') }} as i
inner join {{ ref('fct_orders') }} as o using (order_id)
left join {{ ref('stg_products') }} as p using (product_id)
left join {{ ref('stg_sellers') }} as s using (seller_id)
