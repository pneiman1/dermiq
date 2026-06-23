with source as (

    select * from {{ source('nextech', 'appointments') }}

),

renamed as (

    select
        trim(appointment_id)                     as appointment_id,
        trim(patient_id)                         as patient_id,
        trim(provider_id)                        as provider_id,
        trim(appointment_type)                   as appointment_type,
        cast(scheduled_start as timestamp_tz)    as scheduled_start,
        cast(scheduled_end as timestamp_tz)      as scheduled_end,
        cast(actual_arrival as timestamp_tz)     as actual_arrival,
        cast(actual_departure as timestamp_tz)   as actual_departure,
        trim(status)                             as appointment_status,
        cast(booking_lead_time_hours as integer) as booking_lead_time_hours,
        cast(created_at as timestamp_tz)         as created_at,
        cast(updated_at as timestamp_tz)         as updated_at,
        cast(_ingested_at as timestamp_tz)       as ingested_at

    from source

)

select * from renamed
