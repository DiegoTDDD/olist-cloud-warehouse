select
    order_id,
    customer_id,
    order_status as status,
    order_purchase_timestamp as purchased_at,
    order_approved_at as approved_at,
    order_delivered_carrier_date as delivered_to_carrier_at,
    order_delivered_customer_date as delivered_to_customer_at,
    -- the promise is a date; the source stores it as midnight
    date(order_estimated_delivery_date) as estimated_delivery_date
from {{ source('raw', 'orders') }}
