select
    order_id,
    payment_sequential,
    payment_type,
    payment_installments,
    payment_value,
    _batch as source_batch
from {{ source('raw', 'order_payments') }}
qualify row_number() over (partition by order_id, payment_sequential order by _batch desc) = 1
