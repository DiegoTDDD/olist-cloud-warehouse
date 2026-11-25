-- Every month key falls inside the integer-range partition spec (201601-201812). A key outside
-- it would land in the __UNPARTITIONED__ partition, where queries cannot prune it.
select purchase_month_key
from {{ ref('fct_orders') }}
where purchase_month_key not between 201601 and 201812
group by 1
