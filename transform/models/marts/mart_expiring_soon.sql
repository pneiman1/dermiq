-- Inventory tab — expiring soon (chunk-11): one row per on-hand lot with stock
-- remaining and a future expiry. Quantity remaining is the received quantity net
-- of everything drawn against the lot (consumption / waste / expiry). value at
-- risk = remaining * per-lot actual cost. Urgency buckets the days to expiry.

{{ config(materialized='table') }}

with lots as (

    select * from {{ ref('stg_nextech__inventory_lots') }}

),

units as (

    select * from {{ ref('stg_nextech__inventory_units') }}

),

drawn_per_lot as (

    select
        lot_id,
        sum(quantity) as quantity_drawn
    from {{ ref('int_inventory_movements') }}
    where lot_id is not null
    group by 1

),

final as (

    select
        l.lot_id,
        l.sku,
        u.product_name                                             as sku_name,
        u.category,
        l.lot_number,
        l.expiry_date,
        datediff('day', current_date, l.expiry_date)               as days_to_expiry,
        cast(l.received_quantity - coalesce(d.quantity_drawn, 0) as number(18, 4)) as quantity_remaining,
        cast(
            (l.received_quantity - coalesce(d.quantity_drawn, 0)) * l.unit_cost_actual
            as number(18, 4)
        )                                                          as estimated_value_at_risk,
        case
            when datediff('day', current_date, l.expiry_date) < 14 then 'critical'
            when datediff('day', current_date, l.expiry_date) < 30 then 'warning'
            when datediff('day', current_date, l.expiry_date) < 60 then 'watch'
            else 'future'
        end                                                        as urgency_level

    from lots l
    left join units u        on l.sku = u.unit_id
    left join drawn_per_lot d on l.lot_id = d.lot_id
    -- Only lots still on hand and not yet expired.
    where l.expiry_date >= current_date
      and (l.received_quantity - coalesce(d.quantity_drawn, 0)) > 0.0001

)

select * from final
