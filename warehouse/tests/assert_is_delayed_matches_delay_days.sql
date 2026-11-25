-- Late exactly when delivered on a later day than promised. Comparing timestamps instead once
-- flagged 1,292 orders delivered on the promised day (olist-analytics).
select order_id, is_delayed, delay_days
from {{ ref('fct_orders') }}
where is_delayed != coalesce(delay_days > 0, false)
