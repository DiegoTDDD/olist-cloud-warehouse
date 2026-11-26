-- The change feeds hold at most one version of a record per batch. A second one would mean a
-- batch was appended twice instead of replacing its partition, and "latest version" would no
-- longer be well defined.
select 'orders' as feed, order_id as record, _batch, count(*) as versions
from {{ source('raw', 'orders') }}
group by order_id, _batch
having count(*) > 1

union all

select 'order_items', concat(order_id, '/', order_item_id), _batch, count(*)
from {{ source('raw', 'order_items') }}
group by order_id, order_item_id, _batch
having count(*) > 1

union all

select 'order_payments', concat(order_id, '/', payment_sequential), _batch, count(*)
from {{ source('raw', 'order_payments') }}
group by order_id, payment_sequential, _batch
having count(*) > 1

union all

select 'order_reviews', concat(review_id, '/', order_id), _batch, count(*)
from {{ source('raw', 'order_reviews') }}
group by review_id, order_id, _batch
having count(*) > 1
