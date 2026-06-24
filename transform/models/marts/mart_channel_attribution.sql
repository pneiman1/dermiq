-- Marketing attribution tab: one row per acquisition channel. Primary metrics are
-- the trailing-twelve-months acquisition cohort (patients whose FIRST visit falls
-- in the TTM window), joined to monthly marketing spend (marketing_spend seed) to
-- produce CAC and LTV:CAC. all-time patient count kept as informational context.
--
-- Note: unknown_count is structurally 0 here — a first-visit-in-TTM cohort cannot
-- contain never-visited patients; kept for shape symmetry with the tier breakdown.

{{ config(materialized='table') }}

with plv as (

    select * from {{ ref('int_patient_lifetime_value') }}
    where not is_deleted

),

channels as (

    select distinct acquisition_channel from plv

),

ttm_cohort as (

    select
        acquisition_channel,
        count(*)                            as patients_acquired_ttm,
        sum(total_revenue)                  as total_revenue_ttm,
        avg(annual_revenue_run_rate)        as avg_ltv_run_rate_ttm,
        count_if(ltv_tier = 'vip')          as vip_count,
        count_if(ltv_tier = 'high')         as high_count,
        count_if(ltv_tier = 'standard')     as standard_count,
        count_if(ltv_tier = 'low')          as low_count,
        count_if(ltv_tier = 'unknown')      as unknown_count
    from plv
    where first_visit_date >= dateadd('month', -12, current_date)
    group by 1

),

alltime as (

    select acquisition_channel, count(*) as total_patients_alltime
    from plv
    group by 1

),

spend as (

    select
        channel                             as acquisition_channel,
        sum(spend_usd)                      as spend_ttm
    from {{ ref('marketing_spend') }}
    where month_start >= dateadd('month', -12, current_date)
    group by 1

),

final as (

    select
        c.acquisition_channel,

        coalesce(t.patients_acquired_ttm, 0)                        as patients_acquired_ttm,
        cast(coalesce(t.total_revenue_ttm, 0) as number(18, 4))     as total_revenue_ttm,
        cast(t.avg_ltv_run_rate_ttm as number(18, 4))              as avg_ltv_run_rate_ttm,
        coalesce(t.vip_count, 0)                                    as vip_count,
        coalesce(t.high_count, 0)                                   as high_count,
        coalesce(t.standard_count, 0)                              as standard_count,
        coalesce(t.low_count, 0)                                    as low_count,
        coalesce(t.unknown_count, 0)                               as unknown_count,

        coalesce(a.total_patients_alltime, 0)                       as total_patients_alltime,

        cast(coalesce(s.spend_ttm, 0) as number(18, 4))             as spend_ttm,
        cast(coalesce(s.spend_ttm, 0)
             / nullif(t.patients_acquired_ttm, 0) as number(18, 4)) as cac_ttm,
        cast(
            t.avg_ltv_run_rate_ttm
              / nullif(coalesce(s.spend_ttm, 0) / nullif(t.patients_acquired_ttm, 0), 0)
            as number(10, 4)
        )                                                          as ltv_cac_ratio_ttm,

        case
            when coalesce(s.spend_ttm, 0) = 0 then 'organic'
            when t.avg_ltv_run_rate_ttm
                   / nullif(s.spend_ttm / nullif(t.patients_acquired_ttm, 0), 0) >= 4 then 'excellent'
            when t.avg_ltv_run_rate_ttm
                   / nullif(s.spend_ttm / nullif(t.patients_acquired_ttm, 0), 0) >= 2 then 'healthy'
            when t.avg_ltv_run_rate_ttm
                   / nullif(s.spend_ttm / nullif(t.patients_acquired_ttm, 0), 0) >= 1 then 'marginal'
            else 'unprofitable'
        end                                                        as channel_health

    from channels c
    left join ttm_cohort t on c.acquisition_channel = t.acquisition_channel
    left join alltime a    on c.acquisition_channel = a.acquisition_channel
    left join spend s      on c.acquisition_channel = s.acquisition_channel

)

select * from final
