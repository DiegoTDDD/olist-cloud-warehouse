-- The decision mart: how much does each day of delay cost in customer rating? It answers
-- whether logistics money should go to avoiding delays or to shortening long ones.
with delivered as (
    select
        case
            when delay_days < 0 then -1
            when delay_days >= 10 then 10
            else delay_days
        end as delay_bucket_days,
        review_score
    from {{ ref('fct_orders') }}
    where status = 'delivered' and delay_days is not null
)

select
    delay_bucket_days,
    case
        when delay_bucket_days = -1 then 'early'
        when delay_bucket_days = 0 then 'on the promised day'
        when delay_bucket_days = 10 then '10 or more days late'
        else concat(cast(delay_bucket_days as string), ' days late')
    end as delay_bucket,
    count(*) as orders,
    countif(review_score is not null) as reviewed_orders,
    round(avg(review_score), 2) as avg_review_score,
    round(safe_divide(countif(review_score = 1), countif(review_score is not null)), 4) as one_star_share
from delivered
group by delay_bucket_days
