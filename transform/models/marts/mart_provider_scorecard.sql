-- Provider performance tab: one row per provider. Primary metrics are trailing
-- twelve months (TTM) because cosmetic derm moves fast and all-time totals
-- overweight tenure; all-time totals are kept as informational context.
-- revenue_rank ranks on TTM revenue-per-hour (productivity), not raw revenue.

{{ config(materialized='table') }}

with visits as (

    select * from {{ ref('int_visit_economics') }}

),

ttm as (

    select
        provider_id,
        count(*)                            as visits_ttm,
        sum(net_revenue)                    as revenue_ttm,
        count(distinct visit_date)          as active_days_ttm,
        sum(actual_duration_min) / 60.0     as productive_hours_ttm,
        count_if(had_cross_sell)            as cross_sell_visits_ttm
    from visits
    where visit_date >= dateadd('month', -12, current_date)
    group by 1

),

alltime as (

    select
        provider_id,
        count(*)                            as total_visits_alltime,
        sum(net_revenue)                    as total_revenue_alltime,
        max(visit_date)                     as last_visit_date
    from visits
    group by 1

),

final as (

    select
        p.provider_id,
        p.full_name                                                 as provider_name,
        p.provider_role,
        p.specialties,

        coalesce(t.visits_ttm, 0)                                   as visits_ttm,
        cast(coalesce(t.revenue_ttm, 0) as number(18, 4))           as revenue_ttm,
        cast(t.revenue_ttm / nullif(t.visits_ttm, 0) as number(18, 4))         as avg_ticket_ttm,
        cast(t.revenue_ttm / nullif(t.productive_hours_ttm, 0) as number(18, 4)) as revenue_per_hour_ttm,
        cast(t.cross_sell_visits_ttm / nullif(t.visits_ttm, 0) as number(10, 4)) as cross_sell_rate_ttm,
        cast(coalesce(t.productive_hours_ttm, 0) as number(10, 2))  as productive_hours_ttm,
        coalesce(t.active_days_ttm, 0)                              as active_days_ttm,

        coalesce(a.total_visits_alltime, 0)                         as total_visits_alltime,
        cast(coalesce(a.total_revenue_alltime, 0) as number(18, 4)) as total_revenue_alltime,
        a.last_visit_date,

        rank() over (
            order by t.revenue_ttm / nullif(t.productive_hours_ttm, 0) desc nulls last
        )                                                           as revenue_rank

    from {{ ref('stg_nextech__providers') }} p
    left join ttm t      on p.provider_id = t.provider_id
    left join alltime a  on p.provider_id = a.provider_id

)

select * from final
