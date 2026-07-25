with source as (

    select * from {{ source('nextech', 'inventory_current_stock') }}

),

renamed as (

    select
        trim(sku)                                 as sku,
        cast(on_hand_quantity as number(18, 4))   as on_hand_quantity,
        cast(oldest_lot_expiry as date)           as oldest_lot_expiry,
        on_hand_lots                              as on_hand_lots,      -- JSON text
        cast(last_transaction_at as date)         as last_transaction_at,
        cast(_ingested_at as timestamp_tz)        as ingested_at

    from source

)

select * from renamed
