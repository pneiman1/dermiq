with source as (

    select * from {{ source('nextech', 'inventory_units') }}

),

renamed as (

    select
        trim(unit_id)                            as unit_id,
        trim(product_name)                       as product_name,
        trim(category)                           as category,
        trim(unit_of_measure)                    as unit_of_measure,
        trim(service_code)                       as service_code,
        cast(units_per_service as number(18, 4)) as units_per_service,
        -- normalize source NUMBER(20,4) to the NUMBER(18,4) monetary standard
        cast(unit_cost as number(18, 4))         as unit_cost,
        cast(shelf_life_months as integer)       as shelf_life_months,
        cast(par_level as number(18, 4))         as par_level,
        cast(created_at as timestamp_tz)         as created_at,
        cast(updated_at as timestamp_tz)         as updated_at,
        cast(_ingested_at as timestamp_tz)       as ingested_at

    from source

)

select * from renamed
