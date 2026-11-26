-- The latest version of each review: the answer time arrives after the review itself. A review
-- id can belong to more than one order in the source, so the key is (review_id, order_id).
select
    review_id,
    order_id,
    review_score,
    review_creation_date as reviewed_at,
    review_answer_timestamp as answered_at,
    _batch as source_batch
from {{ source('raw', 'order_reviews') }}
qualify row_number() over (partition by review_id, order_id order by _batch desc) = 1
