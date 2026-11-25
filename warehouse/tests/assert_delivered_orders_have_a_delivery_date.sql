-- 8 delivered orders in the source have no delivery date; more than 10 means a load problem.
{{ config(warn_if='> 8', error_if='> 10') }}
select order_id
from {{ ref('stg_orders') }}
where status = 'delivered' and delivered_to_customer_at is null
