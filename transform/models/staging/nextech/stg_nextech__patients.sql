with source as (

    select * from {{ source('nextech', 'patients') }}

),

renamed as (

    select
        trim(patient_id)                         as patient_id,
        trim(first_name)                         as first_name,
        trim(last_name)                          as last_name,
        cast(date_of_birth as date)              as date_of_birth,
        trim(gender)                             as gender,
        trim(address_zip)                        as zip_code,
        trim(primary_phone)                      as primary_phone,
        lower(trim(primary_email))               as primary_email,
        trim(source_channel)                     as source_channel,
        cast(created_at as timestamp_tz)         as created_at,
        cast(updated_at as timestamp_tz)         as updated_at,
        cast(deleted_at as timestamp_tz)         as deleted_at,
        (deleted_at is not null)                 as is_deleted,
        cast(_ingested_at as timestamp_tz)       as ingested_at

    from source

)

select * from renamed
