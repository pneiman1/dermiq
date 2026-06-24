-- Revenue dashboard tab: one row per calendar day. Combines completed-visit
-- economics (keyed on visit_date) with the appointment funnel (keyed on
-- scheduled_date) and new-patient counts, via a full outer join so days with
-- only no-shows/cancellations still appear.

{{ config(materialized='table', cluster_by=['date_day']) }}

with econ as (

    select
        visit_date                          as date_day,
        count(*)                            as completed_visits,
        sum(net_revenue)                    as net_revenue,
        sum(rev_injectable)                 as rev_injectable,
        sum(rev_device)                     as rev_device,
        sum(rev_skincare)                   as rev_skincare,
        sum(rev_membership)                 as rev_membership,
        sum(rev_surgical)                   as rev_surgical,
        sum(rev_consult)                    as rev_consult,
        sum(line_item_count)                as line_items,
        count(distinct patient_id)          as distinct_patients,
        count(distinct provider_id)         as distinct_providers
    from {{ ref('int_visit_economics') }}
    group by 1

),

disp as (

    select
        scheduled_date                      as date_day,
        count(*)                            as scheduled_appointments,
        count_if(is_no_show)                as no_show_count,
        count_if(is_cancelled)              as cancelled_count
    from {{ ref('int_appointment_disposition') }}
    group by 1

),

new_pat as (

    select
        first_visit_date                    as date_day,
        count(*)                            as new_patients
    from {{ ref('int_patient_lifetime_value') }}
    where first_visit_date is not null
    group by 1

),

final as (

    select
        coalesce(e.date_day, d.date_day, n.date_day)                 as date_day,

        coalesce(e.completed_visits, 0)                             as completed_visits,
        cast(coalesce(e.net_revenue, 0) as number(18, 4))           as net_revenue,
        cast(coalesce(e.net_revenue, 0)
             / nullif(e.completed_visits, 0) as number(18, 4))      as avg_ticket,

        cast(coalesce(e.rev_injectable, 0)  as number(18, 4))       as rev_injectable,
        cast(coalesce(e.rev_device, 0)      as number(18, 4))       as rev_device,
        cast(coalesce(e.rev_skincare, 0)    as number(18, 4))       as rev_skincare,
        cast(coalesce(e.rev_membership, 0)  as number(18, 4))       as rev_membership,
        cast(coalesce(e.rev_surgical, 0)    as number(18, 4))       as rev_surgical,
        cast(coalesce(e.rev_consult, 0)     as number(18, 4))       as rev_consult,

        coalesce(e.line_items, 0)                                   as line_items,
        coalesce(e.distinct_patients, 0)                            as distinct_patients,
        coalesce(e.distinct_providers, 0)                           as distinct_providers,
        coalesce(n.new_patients, 0)                                 as new_patients,

        coalesce(d.scheduled_appointments, 0)                       as scheduled_appointments,
        coalesce(d.no_show_count, 0)                                as no_show_count,
        coalesce(d.cancelled_count, 0)                              as cancelled_count,
        cast(coalesce(d.no_show_count, 0)
             / nullif(d.scheduled_appointments, 0) as number(10, 4)) as no_show_rate

    from econ e
    full outer join disp d on e.date_day = d.date_day
    full outer join new_pat n on coalesce(e.date_day, d.date_day) = n.date_day

)

select * from final
