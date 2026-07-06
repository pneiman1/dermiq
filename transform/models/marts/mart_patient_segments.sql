-- One row per discovered patient segment (k-means cluster). Consumed by the
-- AI Studio tab. Reads the ML-produced assignments (source 'ml') joined to the
-- patient LTV + feature grains.

{{ config(materialized='table') }}

with assign as (

    select patient_id, cluster_id, cluster_name
    from {{ source('ml', 'int_patient_cluster_assignments') }}

),

plv as (select * from {{ ref('int_patient_lifetime_value') }}),
feat as (select * from {{ ref('int_patient_features') }}),

base as (

    select
        a.cluster_id,
        max(a.cluster_name)                      as cluster_name,
        count(*)                                 as patient_count,
        avg(p.total_revenue)                     as avg_ltv,
        avg(p.annual_revenue_run_rate)           as avg_annual_run_rate,
        avg(p.recency_days)                      as avg_recency_days,
        count_if(p.recency_tier = 'active')      as active_patient_count
    from assign a
    join plv p on a.patient_id = p.patient_id
    group by 1

),

-- Most-visited provider across a cluster's members.
cluster_provider as (

    select cluster_id, provider_id as top_provider_id
    from (
        select a.cluster_id, v.provider_id, count(*) as n
        from assign a
        join {{ ref('int_visit_economics') }} v on a.patient_id = v.patient_id
        group by 1, 2
    )
    qualify row_number() over (partition by cluster_id order by n desc, provider_id) = 1

),

-- Most common dominant category across a cluster's members.
cluster_category as (

    select cluster_id, dominant_category
    from (
        select a.cluster_id, f.dominant_category, count(*) as n
        from assign a
        join feat f on a.patient_id = f.patient_id
        group by 1, 2
    )
    qualify row_number() over (partition by cluster_id order by n desc, dominant_category) = 1

),

urgent as (

    select a.cluster_id, count(*) as urgent_recall_count
    from assign a
    join {{ ref('mart_recall_queue') }} r
      on a.patient_id = r.patient_id and r.recall_priority = 'urgent'
    group by 1

),

final as (

    select
        b.cluster_id,
        b.cluster_name,
        b.patient_count,
        cast(b.avg_ltv as number(18, 4))              as avg_ltv,
        cast(b.avg_annual_run_rate as number(18, 4))  as avg_annual_run_rate,
        cc.dominant_category,
        cp.top_provider_id,
        prov.full_name                                as top_provider_name,
        cast(round(b.avg_recency_days) as integer)    as avg_recency_days,
        coalesce(u.urgent_recall_count, 0)            as urgent_recall_count,
        b.active_patient_count
    from base b
    left join cluster_provider cp on b.cluster_id = cp.cluster_id
    left join cluster_category cc on b.cluster_id = cc.cluster_id
    left join urgent u on b.cluster_id = u.cluster_id
    left join {{ ref('stg_nextech__providers') }} prov on cp.top_provider_id = prov.provider_id

)

select * from final
