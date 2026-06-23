-- One row per COMPLETED appointment with its economics: revenue (total and by
-- service category), line-item count, cross-sell flags, and actual duration.
-- Non-completed appointments carry no revenue/duration and are handled by the
-- sibling int_appointment_disposition.

with appointments as (

    select *
    from {{ ref('stg_nextech__appointments') }}
    where appointment_status = 'completed'

),

transactions as (

    select * from {{ ref('stg_nextech__transactions') }}

),

txn_agg as (

    select
        appointment_id,
        sum(net_amount)                                                as net_revenue,
        count(*)                                                       as line_item_count,
        count(distinct service_category)                              as distinct_category_count,
        sum(iff(service_category = 'injectable',      net_amount, 0))  as rev_injectable,
        sum(iff(service_category = 'energy_device',   net_amount, 0))  as rev_device,
        sum(iff(service_category = 'skincare_retail', net_amount, 0))  as rev_skincare,
        sum(iff(service_category = 'membership',      net_amount, 0))  as rev_membership,
        sum(iff(service_category = 'surgical',        net_amount, 0))  as rev_surgical,
        sum(iff(service_category = 'consult',         net_amount, 0))  as rev_consult
    from transactions
    where appointment_id is not null
    group by appointment_id

),

final as (

    select
        a.appointment_id,
        a.patient_id,
        a.provider_id,
        cast(a.scheduled_start as date)                               as visit_date,

        cast(coalesce(t.net_revenue, 0)     as number(18, 4))         as net_revenue,
        coalesce(t.line_item_count, 0)                               as line_item_count,

        cast(coalesce(t.rev_injectable, 0)  as number(18, 4))         as rev_injectable,
        cast(coalesce(t.rev_device, 0)      as number(18, 4))         as rev_device,
        cast(coalesce(t.rev_skincare, 0)    as number(18, 4))         as rev_skincare,
        cast(coalesce(t.rev_membership, 0)  as number(18, 4))         as rev_membership,
        cast(coalesce(t.rev_surgical, 0)    as number(18, 4))         as rev_surgical,
        cast(coalesce(t.rev_consult, 0)     as number(18, 4))         as rev_consult,

        coalesce(t.rev_injectable, 0) > 0                            as had_injectable,
        coalesce(t.rev_device, 0) > 0                               as had_device,
        coalesce(t.rev_skincare, 0) > 0                            as had_skincare,
        coalesce(t.distinct_category_count, 0) > 1                  as had_cross_sell,

        datediff('minute', a.actual_arrival, a.actual_departure)    as actual_duration_min

    from appointments a
    left join txn_agg t on a.appointment_id = t.appointment_id

)

select * from final
