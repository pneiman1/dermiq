with source as (

    select * from {{ source('nextech', 'inventory_lots') }}

),

renamed as (

    select
        trim(lot_id)                              as lot_id,
        trim(sku)                                 as sku,
        trim(lot_number)                          as lot_number,
        cast(received_quantity as number(18, 4))  as received_quantity,
        cast(received_date as date)               as received_date,
        cast(expiry_date as date)                 as expiry_date,
        -- normalize source NUMBER(20,4) to the NUMBER(18,4) monetary standard
        cast(unit_cost_actual as number(18, 4))   as unit_cost_actual,
        cast(created_at as timestamp_tz)          as created_at,
        cast(_ingested_at as timestamp_tz)        as ingested_at

    from source

)

select * from renamed
