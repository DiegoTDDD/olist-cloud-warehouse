select
    review_id,
    order_id,
    review_score,
    review_creation_date as reviewed_at,
    review_answer_timestamp as answered_at
from {{ source('raw', 'order_reviews') }}
