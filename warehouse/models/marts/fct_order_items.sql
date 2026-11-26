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
    cluster_by=["category", "seller_state"],
    on_schema_change="fail"
  )
}}
-- Incremental like fct_orders (docs/adr/0006): items arrive once, with their order, so the
-- months to rebuild are the purchase months of items newer than the watermark.

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
    i.freight_value,
    i.source_batch
from {{ ref('stg_order_items') }} as i
inner join {{ ref('fct_orders') }} as o using (order_id)
left join {{ ref('stg_products') }} as p using (product_id)
left join {{ ref('stg_sellers') }} as s using (seller_id)
{% if is_incremental() %}
where o.purchase_month_key in (
    select o2.purchase_month_key
    from {{ ref('stg_order_items') }} as i2
    inner join {{ ref('fct_orders') }} as o2 using (order_id)
    where i2.source_batch > (select coalesce(max(source_batch), -1) from {{ this }})
)
{% endif %}
