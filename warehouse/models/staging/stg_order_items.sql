-- Items arrive once, with their order; the window only guards against a batch loaded twice.
select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    shipping_limit_date as shipping_limit_at,
    price,
    freight_value,
    _batch as source_batch
from {{ source('raw', 'order_items') }}
qualify row_number() over (partition by order_id, order_item_id order by _batch desc) = 1
