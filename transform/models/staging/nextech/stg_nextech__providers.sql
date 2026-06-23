with source as (

    select * from {{ source('nextech', 'providers') }}

),

renamed as (

    select
        trim(provider_id)                        as provider_id,
        trim(full_name)                          as full_name,
        trim(role)                               as provider_role,
        -- npi_number, hire_date, termination_date are unpopulated in source
        -- (the seed loader inserts NULL), so write_pandas lands them as NUMBER
        -- in raw. Bridge through varchar so the DATE/text casts are legal; the
        -- try_cast also stays correct if real values appear later.
        trim(cast(npi_number as varchar))        as npi_number,
        trim(specialties)                        as specialties,
        try_cast(cast(hire_date as varchar) as date)        as hire_date,
        try_cast(cast(termination_date as varchar) as date) as termination_date,
        cast(created_at as timestamp_tz)         as created_at,
        cast(updated_at as timestamp_tz)         as updated_at,
        cast(_ingested_at as timestamp_tz)       as ingested_at

    from source

)

select * from renamed
