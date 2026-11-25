# 0004: Integer-range partitions by month, clustered by state and status

## Context

Analysts filter orders by period, by customer state and by status. On demand, BigQuery bills
the bytes a query reads, so the table layout decides what every question costs. Date
partitioning is the usual choice, but in the sandbox every date partition older than 60 days
expires: a table of 2016-2018 orders partitioned by date would be emptied on creation.

## Decision

`fct_orders` and `fct_order_items` are partitioned by an integer YYYYMM key
(`purchase_month_key`, range 201601 to 201901) and clustered by the columns analysts filter
on next (`customer_state`, `status`; for items, `category`, `seller_state`). A dbt test checks
that no key falls outside the range, where rows would land in the unpartitioned bucket and
never be pruned. The cost report measures the effect on real queries against an unpartitioned
copy of the same table.

## Consequences

Queries that filter on the month key read only those months. Integer-range partitions work
the same outside the sandbox, so the choice does not need revisiting with billing; on a
billed project, date partitioning would also be an option. Billing rounds each query up to
10 MB, so on a table this size the bill does not change; the bytes read are what scale.
