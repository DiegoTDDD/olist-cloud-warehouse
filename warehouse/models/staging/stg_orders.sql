-- The latest version of each order. raw.orders holds every version the daily replay delivered
-- (an order is bought, then approved, shipped and delivered on different days).
select
    order_id,
    customer_id,
    order_status as status,
    order_purchase_timestamp as purchased_at,
    order_approved_at as approved_at,
    order_delivered_carrier_date as delivered_to_carrier_at,
    order_delivered_customer_date as delivered_to_customer_at,
    -- the promise is a date; the source stores it as midnight
    date(order_estimated_delivery_date) as estimated_delivery_date,
    _batch as source_batch
from {{ source('raw', 'orders') }}
qualify row_number() over (partition by order_id order by _batch desc) = 1
