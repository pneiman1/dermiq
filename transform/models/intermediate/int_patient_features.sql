-- One row per cluster-eligible patient: behavioral features for k-means.
-- Eligible = not soft-deleted, with at least one completed visit (real behavior).

{{ config(materialized='table') }}

with plv as (

    select *
    from {{ ref('int_patient_lifetime_value') }}
    where not is_deleted and total_visits >= 1

),

visits as (

    select * from {{ ref('int_visit_economics') }}

),

cat_agg as (

    select
        patient_id,
        sum(net_revenue)                as rev_total,
        count_if(rev_injectable > 0)    as visits_injectable,
        count_if(rev_device > 0)        as visits_device,
        count_if(rev_skincare > 0)      as visits_skincare,
        count_if(rev_membership > 0)    as visits_membership,
        count_if(rev_surgical > 0)      as visits_surgical,
        count_if(rev_consult > 0)       as visits_consult,
        sum(rev_injectable)             as sum_injectable,
        sum(rev_device)                 as sum_device,
        sum(rev_skincare)               as sum_skincare,
        sum(rev_membership)             as sum_membership,
        sum(rev_surgical)               as sum_surgical,
        sum(rev_consult)                as sum_consult
    from visits
    group by 1

),

dominant_provider as (

    select patient_id, provider_id as dominant_provider_id
    from (
        select patient_id, provider_id, count(*) as n
        from visits
        group by 1, 2
    )
    qualify row_number() over (partition by patient_id order by n desc, provider_id) = 1

),

final as (

    select
        p.patient_id,
        p.total_visits,
        p.total_revenue,
        p.annual_revenue_run_rate,
        p.recency_days,
        p.ltv_tier,
        p.acquisition_channel,

        c.visits_injectable,
        c.visits_device,
        c.visits_skincare,
        c.visits_membership,
        c.visits_surgical,
        c.visits_consult,

        cast(div0(c.sum_injectable, c.rev_total) as number(10, 6)) as rev_injectable_share,
        cast(div0(c.sum_device, c.rev_total) as number(10, 6))     as rev_device_share,
        cast(div0(c.sum_skincare, c.rev_total) as number(10, 6))   as rev_skincare_share,
        cast(div0(c.sum_membership, c.rev_total) as number(10, 6)) as rev_membership_share,
        cast(div0(c.sum_surgical, c.rev_total) as number(10, 6))   as rev_surgical_share,
        cast(div0(c.sum_consult, c.rev_total) as number(10, 6))    as rev_consult_share,

        cast(
            p.total_visits
              / greatest(0.25, datediff('day', p.first_visit_date, current_date) / 365.0)
            as number(10, 4)
        )                                                          as avg_visits_per_year,

        dp.dominant_provider_id,

        case greatest(c.sum_injectable, c.sum_device, c.sum_skincare,
                      c.sum_membership, c.sum_surgical, c.sum_consult)
            when c.sum_injectable then 'injectable'
            when c.sum_device     then 'energy_device'
            when c.sum_skincare   then 'skincare_retail'
            when c.sum_membership then 'membership'
            when c.sum_surgical   then 'surgical'
            else                       'consult'
        end                                                        as dominant_category

    from plv p
    join cat_agg c on p.patient_id = c.patient_id
    join dominant_provider dp on p.patient_id = dp.patient_id

)

select * from final
