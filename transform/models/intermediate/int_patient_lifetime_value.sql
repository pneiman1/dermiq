-- One row per patient (including soft-deleted) with lifetime visit/revenue
-- aggregates and derived tiers. Visit aggregates come from int_visit_economics
-- (completed visits only). ltv_tier is based on an ANNUALIZED revenue run-rate,
-- not raw lifetime revenue, so newer and older patients are compared fairly.
--
-- recency_days / recency_tier / run-rate are evaluated as-of build date
-- (current_date), so this table is intentionally non-deterministic across days.

with patients as (

    select * from {{ ref('stg_nextech__patients') }}

),

visit_agg as (

    select
        patient_id,
        min(visit_date)         as first_visit_date,
        max(visit_date)         as last_visit_date,
        count(*)                as total_visits,
        sum(net_revenue)        as total_revenue
    from {{ ref('int_visit_economics') }}
    group by patient_id

),

enriched as (

    select
        p.patient_id,
        v.first_visit_date,
        v.last_visit_date,
        coalesce(v.total_visits, 0)                                   as total_visits,
        cast(coalesce(v.total_revenue, 0) as number(18, 4))           as total_revenue,
        datediff('day', v.last_visit_date, current_date)             as recency_days,
        -- Annualize over tenure; floor the denominator at 0.25y so a patient with
        -- <3 months of history isn't extrapolated to an absurd run-rate.
        cast(
            coalesce(v.total_revenue, 0)
              / greatest(0.25, datediff('year', v.first_visit_date, current_date))
            as number(18, 4)
        )                                                            as annual_revenue_run_rate,
        p.source_channel                                            as acquisition_channel,
        p.is_deleted
    from patients p
    left join visit_agg v on p.patient_id = v.patient_id

),

final as (

    select
        patient_id,
        first_visit_date,
        last_visit_date,
        total_visits,
        total_revenue,
        annual_revenue_run_rate,
        recency_days,

        case
            when total_visits = 0          then null
            when recency_days <= 120       then 'active'
            when recency_days <= 240       then 'lapsing'
            when recency_days <= 540       then 'lapsed'
            else                                'dormant'
        end                                                          as recency_tier,

        -- Never-visited patients are 'unknown' (don't pre-judge new signups);
        -- tiers above that are on annualized run-rate ($/yr).
        case
            when total_visits = 0                       then 'unknown'
            when annual_revenue_run_rate >= 8000        then 'vip'
            when annual_revenue_run_rate >= 3000        then 'high'
            when annual_revenue_run_rate >= 800         then 'standard'
            else                                              'low'
        end                                                          as ltv_tier,

        acquisition_channel,
        is_deleted

    from enriched

)

select * from final
