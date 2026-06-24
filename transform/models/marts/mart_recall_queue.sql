-- RAG / outreach consumer: one row per patient who should be recalled. Lapsing or
-- lapsed, not soft-deleted, with at least one prior visit (active patients don't
-- need recall; dormant are too cold; never-visited go to a separate nurture track).
-- Carries contact info and last provider so outreach can say "rebook with Dr. X".

{{ config(materialized='table', cluster_by=['last_visit_date']) }}

with plv as (

    select *
    from {{ ref('int_patient_lifetime_value') }}
    where recency_tier in ('lapsing', 'lapsed')
      and not is_deleted
      and total_visits >= 1

),

last_visit as (

    select
        patient_id,
        provider_id as last_provider_id
    from {{ ref('int_visit_economics') }}
    qualify row_number() over (partition by patient_id order by visit_date desc) = 1

),

final as (

    select
        plv.patient_id,
        pat.first_name,
        pat.last_name,
        pat.primary_email,
        pat.primary_phone,
        plv.acquisition_channel,

        plv.last_visit_date,
        plv.recency_days,
        plv.recency_tier,

        plv.total_visits,
        plv.total_revenue,
        plv.annual_revenue_run_rate,
        plv.ltv_tier,

        lv.last_provider_id,
        prov.full_name                                              as last_provider_name,

        case
            when plv.ltv_tier in ('vip', 'high') and plv.recency_tier = 'lapsing' then 'urgent'
            when plv.ltv_tier in ('vip', 'high') and plv.recency_tier = 'lapsed'  then 'high'
            when plv.ltv_tier = 'standard'                                        then 'medium'
            else                                                                       'low'
        end                                                         as recall_priority

    from plv
    join {{ ref('stg_nextech__patients') }} pat on plv.patient_id = pat.patient_id
    left join last_visit lv on plv.patient_id = lv.patient_id
    left join {{ ref('stg_nextech__providers') }} prov on lv.last_provider_id = prov.provider_id

)

select * from final
