with source as (

    select * from {{ source('nextech', 'services') }}

),

renamed as (

    select
        trim(service_code)                       as service_code,
        trim(service_name)                       as service_name,
        trim(category)                           as service_category,
        cast(default_price as number(18, 4))     as default_price,
        cast(default_cost as number(18, 4))      as default_cost,
        cast(typical_duration_min as integer)    as typical_duration_min,
        cast(active as boolean)                  as is_active,
        cast(created_at as timestamp_tz)         as created_at,
        cast(updated_at as timestamp_tz)         as updated_at,
        cast(_ingested_at as timestamp_tz)       as ingested_at

    from source

)

select * from renamed
