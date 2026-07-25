-- Inventory tab — stock status (chunk-11): one row per SKU. On-hand comes from
-- the derived current-stock table; days-of-supply is on-hand over the TTM
-- consumption run-rate; status flags out / low (below par) / overstock. All
-- monetary columns are NUMBER(18,4).

{{ config(materialized='table') }}

with units as (

    select * from {{ ref('stg_nextech__inventory_units') }}

),

stock as (

    select * from {{ ref('stg_nextech__inventory_current_stock') }}

),

consumption_ttm as (

    select
        unit_id,
        sum(quantity) as units_consumed_ttm
    from {{ ref('int_inventory_movements') }}
    where consumed_date >= dateadd('month', -12, current_date)
      and movement_type in ('consumption', 'waste')
    group by 1

),

final as (

    select
        u.unit_id                                                   as sku,
        u.product_name                                             as sku_name,
        u.service_code,
        u.category,
        u.unit_of_measure,

        cast(coalesce(s.on_hand_quantity, 0) as number(18, 4))      as on_hand_quantity,
        cast(u.par_level as number(18, 4))                          as par_level,
        cast(u.unit_cost as number(18, 4))                          as unit_cost,
        cast(coalesce(s.on_hand_quantity, 0) * u.unit_cost as number(18, 4)) as on_hand_value,

        cast(coalesce(c.units_consumed_ttm, 0) as number(18, 4))    as units_consumed_ttm,
        -- Days of supply = on-hand / average daily consumption (TTM run-rate).
        cast(
            coalesce(s.on_hand_quantity, 0)
            / nullif(c.units_consumed_ttm / 365.0, 0)
            as number(18, 2)
        )                                                          as days_of_supply,

        s.oldest_lot_expiry,
        s.last_transaction_at,
        s.on_hand_lots,

        case
            when coalesce(s.on_hand_quantity, 0) <= 0 then 'out'
            when s.on_hand_quantity < u.par_level then 'low'
            when coalesce(c.units_consumed_ttm, 0) > 0
                 and s.on_hand_quantity / (c.units_consumed_ttm / 365.0) > 180 then 'overstock'
            when coalesce(c.units_consumed_ttm, 0) = 0 then 'overstock'
            else 'adequate'
        end                                                        as stock_status

    from units u
    left join stock s           on u.unit_id = s.sku
    left join consumption_ttm c on u.unit_id = c.unit_id

)

select * from final
