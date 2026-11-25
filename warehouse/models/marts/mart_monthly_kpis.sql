select
    purchase_month_key,
    count(*) as orders,
    countif(status = 'delivered') as delivered_orders,
    sum(total_payment_value) as gross_merchandise_value,
    round(safe_divide(countif(is_delayed), countif(status = 'delivered')), 4) as late_rate,
    round(avg(review_score), 2) as avg_review_score,
    count(distinct customer_unique_id) as active_customers
from {{ ref('fct_orders') }}
group by purchase_month_key
