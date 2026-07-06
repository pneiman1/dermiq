-- One row per clustered patient — the drill-in behind each segment card.

{{ config(materialized='table') }}

with assign as (

    select patient_id, cluster_id, cluster_name
    from {{ source('ml', 'int_patient_cluster_assignments') }}

),

plv as (select * from {{ ref('int_patient_lifetime_value') }}),
feat as (select patient_id, dominant_provider_id from {{ ref('int_patient_features') }}),
pat as (select * from {{ ref('stg_nextech__patients') }})

select
    a.patient_id,
    a.cluster_id,
    a.cluster_name,
    pat.first_name,
    pat.last_name,
    p.total_revenue,
    p.annual_revenue_run_rate,
    p.ltv_tier,
    p.recency_tier,
    p.last_visit_date,
    f.dominant_provider_id,
    prov.full_name as dominant_provider_name

from assign a
join plv p on a.patient_id = p.patient_id
join pat on a.patient_id = pat.patient_id
left join feat f on a.patient_id = f.patient_id
left join {{ ref('stg_nextech__providers') }} prov on f.dominant_provider_id = prov.provider_id
