with source as (

    select * from {{ source('nextech', 'inventory_transactions') }}

),

renamed as (

    select
        trim(inventory_transaction_id)             as inventory_transaction_id,
        trim(transaction_id)                       as transaction_id,
        trim(service_code)                         as service_code,
        trim(unit_id)                              as unit_id,
        cast(quantity as number(18, 4))            as quantity,
        -- source unit_cost is NUMBER(20,4), transaction_value NUMBER(38,4);
        -- normalize both to the NUMBER(18,4) monetary standard so downstream
        -- arithmetic with services.default_cost has no precision collision.
        cast(unit_cost as number(18, 4))           as unit_cost,
        cast(transaction_value as number(18, 4))   as transaction_value,
        cast(consumed_date as date)                as consumed_date,
        cast(_ingested_at as timestamp_tz)         as ingested_at

    from source

)

select * from renamed
