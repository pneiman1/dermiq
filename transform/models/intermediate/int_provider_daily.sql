-- One row per provider per day, aggregated from int_visit_economics (completed
-- visits). Productivity + cross-sell metrics that feed provider-performance marts.

with visits as (

    select * from {{ ref('int_visit_economics') }}

),

final as (

    select
        provider_id,
        visit_date                                                          as date_key,

        count(*)                                                            as visit_count,
        cast(sum(net_revenue) as number(18, 4))                            as total_revenue,
        cast(sum(net_revenue) / nullif(count(*), 0) as number(18, 4))      as avg_ticket,

        -- Productive hours = summed actual arrival->departure across the day's
        -- completed visits.
        cast(sum(actual_duration_min) / 60.0 as number(10, 2))             as productive_hours,
        cast(
            sum(net_revenue) / nullif(sum(actual_duration_min) / 60.0, 0)
            as number(18, 4)
        )                                                                  as revenue_per_hour,

        cast(count_if(had_cross_sell) / nullif(count(*), 0) as number(10, 4)) as cross_sell_rate,
        cast(count_if(had_skincare)  / nullif(count(*), 0) as number(10, 4)) as skincare_attach_rate

    from visits
    group by provider_id, visit_date

)

select * from final
