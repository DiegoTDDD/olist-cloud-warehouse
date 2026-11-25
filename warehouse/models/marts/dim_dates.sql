select
    date_day,
    extract(year from date_day) as year,
    extract(quarter from date_day) as quarter,
    extract(month from date_day) as month,
    extract(year from date_day) * 100 + extract(month from date_day) as month_key,
    format_date('%A', date_day) as day_name,
    extract(dayofweek from date_day) in (1, 7) as is_weekend
from unnest(generate_date_array(date '2016-01-01', date '2018-12-31')) as date_day
