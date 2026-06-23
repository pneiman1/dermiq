-- One row per SCHEDULED appointment (any status) with its disposition. Sibling to
-- int_visit_economics, which covers only completed visits. Used by funnel/no-show
-- analytics that need cancelled and no-show rows too.
--
-- days_to_appointment is intentionally omitted: the source has no genuine booking
-- timestamp (appointments.created_at is the row's load-time default, not when the
-- visit was booked), so a lead-time-in-days would be meaningless. The source's
-- booking_lead_time_hours carries lead time instead.

with appointments as (

    select * from {{ ref('stg_nextech__appointments') }}

),

final as (

    select
        appointment_id,
        patient_id,
        provider_id,
        cast(scheduled_start as date)            as scheduled_date,
        appointment_status,

        appointment_status = 'completed'         as is_completed,
        appointment_status = 'no_show'           as is_no_show,
        appointment_status = 'cancelled'         as is_cancelled,

        booking_lead_time_hours

    from appointments

)

select * from final
