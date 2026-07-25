"""Inventory tab endpoints (chunk-11) over the inventory marts. Tenant-gated,
per-request cursor off the shared connection — same conventions as marts.py."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from snowflake.connector.cursor import SnowflakeCursor

from dermiq.api.deps import current_tenant, db_cursor, fetch_models
from dermiq.api.fqn import fq
from dermiq.api.schemas import (
    ExpiringItem,
    InventoryStatusRow,
    InventorySummary,
    TrueMarginRow,
    WasteBySkuRow,
)

router = APIRouter(tags=["inventory"])

# Sort stock rows so the actionable ones (out, then low) float to the top.
_STATUS_RANK = (
    "case stock_status when 'out' then 4 when 'low' then 3 "
    "when 'overstock' then 2 else 1 end"
)


@router.get("/inventory/status", response_model=list[InventoryStatusRow])
def inventory_status(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[InventoryStatusRow]:
    sql = (
        f"select * from {fq('mart', 'mart_inventory_status', tenant)} "
        f"order by {_STATUS_RANK} desc, on_hand_value desc"
    )
    return fetch_models(cur, sql, (), InventoryStatusRow)


@router.get("/inventory/true-margin", response_model=list[TrueMarginRow])
def inventory_true_margin(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[TrueMarginRow]:
    # Biggest surprises first: where catalog margin most overstates true margin.
    sql = (
        f"select * from {fq('mart', 'mart_true_margin_by_service', tenant)} "
        "order by (catalog_margin_pct - true_margin_pct) desc nulls last"
    )
    return fetch_models(cur, sql, (), TrueMarginRow)


@router.get("/inventory/waste", response_model=list[WasteBySkuRow])
def inventory_waste(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    limit: int = Query(50, ge=1, le=200),
) -> list[WasteBySkuRow]:
    """Per-SKU overage waste (TTM): waste units / cost and waste rate vs consumption."""
    inv = fq("int", "int_inventory_movements", tenant)
    sql = (
        "select service_code, service_name, service_category as category, "
        "sum(case when movement_type in ('consumption','waste') then quantity else 0 end) as consumed_units_ttm, "
        "sum(case when movement_type = 'waste' then quantity else 0 end) as waste_units_ttm, "
        "sum(case when movement_type = 'waste' then movement_cost else 0 end) as waste_cost_ttm, "
        "sum(case when movement_type = 'waste' then quantity else 0 end) "
        "  / nullif(sum(case when movement_type in ('consumption','waste') then quantity else 0 end), 0) as waste_rate "
        f"from {inv} "
        "where consumed_date >= dateadd('month', -12, current_date) "
        "and movement_type in ('consumption','waste') "
        "group by 1, 2, 3 "
        "order by waste_rate desc nulls last "
        "limit %s"
    )
    return fetch_models(cur, sql, (limit,), WasteBySkuRow)


@router.get("/inventory/expiring", response_model=list[ExpiringItem])
def inventory_expiring(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    days: int = Query(60, ge=1, le=365),
) -> list[ExpiringItem]:
    """On-hand lots expiring within `days`, soonest first."""
    sql = (
        f"select * from {fq('mart', 'mart_expiring_soon', tenant)} "
        "where days_to_expiry <= %s order by days_to_expiry asc"
    )
    return fetch_models(cur, sql, (days,), ExpiringItem)


@router.get("/inventory/summary", response_model=InventorySummary)
def inventory_summary(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> InventorySummary:
    """KPI strip aggregates across the inventory marts."""
    status = fq("mart", "mart_inventory_status", tenant)
    inv = fq("int", "int_inventory_movements", tenant)
    expiring = fq("mart", "mart_expiring_soon", tenant)
    sql = (
        "select "
        f"(select coalesce(sum(on_hand_value), 0) from {status}) as total_inventory_value, "
        "(select sum(case when movement_type = 'waste' then quantity else 0 end) "
        "  / nullif(sum(case when movement_type in ('consumption','waste') then quantity else 0 end), 0) "
        f"  from {inv} where consumed_date >= dateadd('month', -12, current_date)) as waste_rate_ttm, "
        "(select coalesce(sum(case when movement_type in ('waste','expiry') then movement_cost else 0 end), 0) "
        f"  from {inv} where consumed_date >= dateadd('month', -12, current_date)) as waste_value_ttm, "
        f"(select count(*) from {status} where stock_status in ('out','low')) as items_below_par, "
        f"(select count(*) from {expiring} where days_to_expiry <= 30) as expiring_30d_count, "
        f"(select coalesce(sum(estimated_value_at_risk), 0) from {expiring} where days_to_expiry <= 30) as expiring_30d_value"
    )
    return fetch_models(cur, sql, (), InventorySummary)[0]
