-- Enriched inventory movement grain (chunk-11): one row per consumption / waste /
-- expiry event, with service, product and lot context attached. Marts read from
-- here so the join logic lives in one place. All monetary columns are already
-- NUMBER(18,4) from staging.

with movements as (

    select * from {{ ref('stg_nextech__inventory_transactions') }}

),

units as (

    select * from {{ ref('stg_nextech__inventory_units') }}

),

services as (

    select * from {{ ref('stg_nextech__services') }}

),

lots as (

    select * from {{ ref('stg_nextech__inventory_lots') }}

),

final as (

    select
        m.inventory_transaction_id,
        m.transaction_id,
        m.movement_type,
        m.service_code,
        s.service_name,
        s.service_category,
        m.unit_id,
        u.product_name,
        u.unit_of_measure,
        m.lot_id,
        l.lot_number,
        l.expiry_date                                  as lot_expiry_date,
        cast(m.quantity as number(18, 4))              as quantity,
        cast(m.unit_cost as number(18, 4))             as unit_cost,
        cast(m.transaction_value as number(18, 4))     as movement_cost,
        m.consumed_date

    from movements m
    left join units u    on m.unit_id = u.unit_id
    left join services s on m.service_code = s.service_code
    left join lots l     on m.lot_id = l.lot_id

)

select * from final
