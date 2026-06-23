with source as (

    select * from {{ source('nextech', 'transactions') }}

),

renamed as (

    select
        trim(transaction_id)                     as transaction_id,
        trim(patient_id)                         as patient_id,
        trim(appointment_id)                     as appointment_id,
        trim(provider_id)                        as provider_id,
        trim(service_code)                       as service_code,
        trim(service_category)                   as service_category,
        cast(gross_amount as number(18, 4))      as gross_amount,
        cast(discount_amount as number(18, 4))   as discount_amount,
        cast(net_amount as number(18, 4))        as net_amount,
        cast(alle_redemption_units as integer)   as alle_redemption_units,
        trim(payment_method)                     as payment_method,
        cast(transaction_date as date)           as transaction_date,
        cast(_ingested_at as timestamp_tz)       as ingested_at

    from source

)

select * from renamed
