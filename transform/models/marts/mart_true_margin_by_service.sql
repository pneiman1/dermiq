-- Inventory tab (chunk-11): one row per consumable service — true margin from
-- real cost-of-goods, not list price. "True" margin nets TTM revenue against the
-- actual consumables consumed (inventory_transactions), which runs above the
-- catalog cost because of real acquisition prices and waste. catalog_margin_pct
-- is carried alongside so the gap between assumed and actual margin is visible.
--
-- All monetary columns are NUMBER(18,4): revenue (net_amount), consumables cost
-- (transaction_value) and catalog cost (default_cost) are normalized to the same
-- precision in staging, so the revenue - cost arithmetic here has no
-- NUMBER(20,4)/NUMBER(38,4) precision collision. See docs/DECISIONS.md ADR-010.

{{ config(materialized='table') }}

with services as (

    -- Consumable services only — the ones with a tracked cost-of-goods.
    select s.*
    from {{ ref('stg_nextech__services') }} s
    where s.service_code in (
        select service_code from {{ ref('stg_nextech__inventory_units') }}
    )

),

revenue_ttm as (

    select
        service_code,
        count(*)            as transactions_ttm,
        sum(net_amount)     as revenue_ttm
    from {{ ref('stg_nextech__transactions') }}
    where transaction_date >= dateadd('month', -12, current_date)
    group by 1

),

consumables_ttm as (

    -- True cost-of-goods for a delivered service = product consumed + waste
    -- (overage) during delivery. Expiry write-offs are an inventory loss, not a
    -- per-service delivery cost, so they are excluded here.
    select
        service_code,
        sum(quantity)       as units_consumed_ttm,
        sum(movement_cost)  as consumables_cost_ttm
    from {{ ref('int_inventory_movements') }}
    where consumed_date >= dateadd('month', -12, current_date)
      and movement_type in ('consumption', 'waste')
    group by 1

),

final as (

    select
        s.service_code,
        s.service_name,
        s.service_category,

        coalesce(r.transactions_ttm, 0)                              as transactions_ttm,
        cast(coalesce(u.units_consumed_ttm, 0) as number(18, 4))     as units_consumed_ttm,

        cast(coalesce(r.revenue_ttm, 0) as number(18, 4))            as revenue_ttm,
        cast(coalesce(u.consumables_cost_ttm, 0) as number(18, 4))   as consumables_cost_ttm,
        cast(
            coalesce(r.revenue_ttm, 0) - coalesce(u.consumables_cost_ttm, 0)
            as number(18, 4)
        )                                                            as true_margin_ttm,
        cast(
            (coalesce(r.revenue_ttm, 0) - coalesce(u.consumables_cost_ttm, 0))
            / nullif(r.revenue_ttm, 0)
            as number(10, 4)
        )                                                            as true_margin_pct,

        -- Catalog margin for contrast: what list price vs default_cost implies.
        cast(
            (s.default_price - s.default_cost) / nullif(s.default_price, 0)
            as number(10, 4)
        )                                                            as catalog_margin_pct

    from services s
    left join revenue_ttm r      on s.service_code = r.service_code
    left join consumables_ttm u  on s.service_code = u.service_code
    where coalesce(r.revenue_ttm, 0) > 0

)

select * from final
