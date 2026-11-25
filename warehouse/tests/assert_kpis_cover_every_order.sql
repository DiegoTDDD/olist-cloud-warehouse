-- The monthly KPI mart accounts for every order in the fact table.
select k.orders, f.orders
from (select sum(orders) as orders from {{ ref('mart_monthly_kpis') }}) as k
cross join (select count(*) as orders from {{ ref('fct_orders') }}) as f
where k.orders != f.orders
