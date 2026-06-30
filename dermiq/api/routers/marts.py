"""Data endpoints over the marts (and a couple of intermediate models for grains
the marts don't expose). Every endpoint is tenant-gated via current_tenant and
uses a per-request cursor off the shared connection."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from snowflake.connector.cursor import SnowflakeCursor

from dermiq.api.deps import current_tenant, db_cursor, fetch_models
from dermiq.api.fqn import fq
from dermiq.api.schemas import (
    AcquisitionByMonthRow,
    ChannelAttributionRow,
    DispositionDailyRow,
    FlowByHourRow,
    NoShowByProviderRow,
    PatientTierSummary,
    ProviderRevenueDailyRow,
    RecallSummary,
    ProviderScorecardRow,
    RecallQueueRow,
    RevenueDailyRow,
)

router = APIRouter(tags=["marts"])

# recall_priority ordering for filter (>=) and sort.
PRIORITY_RANK = {"urgent": 4, "high": 3, "medium": 2, "low": 1}

# SQL fragment ranking recall_priority; reused in WHERE and ORDER BY.
_PRIORITY_CASE = (
    "case recall_priority when 'urgent' then 4 when 'high' then 3 "
    "when 'medium' then 2 else 1 end"
)


def _date_range(start: date | None, end: date | None) -> tuple[date, date]:
    """Default to the last 90 days when bounds are omitted."""
    end = end or date.today()
    start = start or (end - timedelta(days=90))
    return start, end


@router.get("/revenue/daily", response_model=list[RevenueDailyRow])
def revenue_daily(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> list[RevenueDailyRow]:
    start, end = _date_range(start_date, end_date)
    sql = (
        f"select * from {fq('mart', 'mart_revenue_daily', tenant)} "
        "where date_day between %s and %s order by date_day desc"
    )
    return fetch_models(cur, sql, (start, end), RevenueDailyRow)


@router.get("/providers/scorecard", response_model=list[ProviderScorecardRow])
def providers_scorecard(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[ProviderScorecardRow]:
    sql = (
        f"select * from {fq('mart', 'mart_provider_scorecard', tenant)} "
        "order by revenue_per_hour_ttm desc nulls last"
    )
    return fetch_models(cur, sql, (), ProviderScorecardRow)


@router.get(
    "/providers/{provider_id}/revenue-daily",
    response_model=list[ProviderRevenueDailyRow],
)
def provider_revenue_daily(
    provider_id: str,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> list[ProviderRevenueDailyRow]:
    start, end = _date_range(start_date, end_date)
    sql = (
        f"select * from {fq('int', 'int_provider_daily', tenant)} "
        "where provider_id = %s and date_key between %s and %s order by date_key"
    )
    return fetch_models(cur, sql, (provider_id, start, end), ProviderRevenueDailyRow)


@router.get("/channels/attribution", response_model=list[ChannelAttributionRow])
def channels_attribution(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[ChannelAttributionRow]:
    sql = (
        f"select * from {fq('mart', 'mart_channel_attribution', tenant)} "
        "order by patients_acquired_ttm desc"
    )
    return fetch_models(cur, sql, (), ChannelAttributionRow)


@router.get("/channels/acquisition-by-month", response_model=list[AcquisitionByMonthRow])
def acquisition_by_month(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    months: int = Query(18, ge=1, le=60),
) -> list[AcquisitionByMonthRow]:
    sql = (
        "select date_trunc('month', first_visit_date)::date as month_start, "
        "acquisition_channel as channel, count(*) as patient_count "
        f"from {fq('int', 'int_patient_lifetime_value', tenant)} "
        "where first_visit_date is not null "
        "and first_visit_date >= dateadd('month', %s, date_trunc('month', current_date)) "
        "group by 1, 2 order by 1, 2"
    )
    return fetch_models(cur, sql, (-months,), AcquisitionByMonthRow)


@router.get("/recall/queue", response_model=list[RecallQueueRow])
def recall_queue(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    limit: int = Query(100, ge=1, le=5000),
    min_priority: Literal["urgent", "high", "medium", "low"] = "low",
) -> list[RecallQueueRow]:
    sql = (
        f"select * from {fq('mart', 'mart_recall_queue', tenant)} "
        f"where {_PRIORITY_CASE} >= %s "
        f"order by {_PRIORITY_CASE} desc, last_visit_date asc "
        "limit %s"
    )
    return fetch_models(cur, sql, (PRIORITY_RANK[min_priority], limit), RecallQueueRow)


@router.get("/recall/summary", response_model=RecallSummary)
def recall_summary(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> RecallSummary:
    """Counts by recall priority + avg recency + latest visit, for the KPI strip
    (the row endpoint is paginated, so aggregates live here)."""
    sql = (
        "select count(*) as total, "
        "count_if(recall_priority = 'urgent') as urgent, "
        "count_if(recall_priority = 'high') as high, "
        "count_if(recall_priority = 'medium') as medium, "
        "count_if(recall_priority = 'low') as low, "
        "round(avg(recency_days))::int as avg_recency_days, "
        "max(last_visit_date) as max_last_visit_date "
        f"from {fq('mart', 'mart_recall_queue', tenant)}"
    )
    return fetch_models(cur, sql, (), RecallSummary)[0]


@router.get("/flow/dispositions", response_model=list[DispositionDailyRow])
def flow_dispositions(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> list[DispositionDailyRow]:
    start, end = _date_range(start_date, end_date)
    sql = (
        "select scheduled_date as day, "
        "count_if(is_completed) as completed, "
        "count_if(is_no_show) as no_show, "
        "count_if(is_cancelled) as cancelled, "
        "count(*) as total, "
        "count_if(is_no_show) / nullif(count(*), 0) as no_show_rate, "
        "count_if(is_cancelled) / nullif(count(*), 0) as cancel_rate "
        f"from {fq('int', 'int_appointment_disposition', tenant)} "
        "where scheduled_date between %s and %s group by 1 order by 1"
    )
    return fetch_models(cur, sql, (start, end), DispositionDailyRow)


@router.get("/flow/by-hour", response_model=list[FlowByHourRow])
def flow_by_hour(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> list[FlowByHourRow]:
    """Appointment volume by ISO day-of-week x hour-of-day, for the heatmap.
    Defaults to the trailing 84 days (12 weeks).

    NOTE: scheduled_start's hours are shifted ~8h in the seeded data (naive local
    times were stored as UTC at ingest), so a plain hour() reads 1am-11am. The
    `timestampadd('hour', 8, ...)` restores clinic-local business hours (9am-7pm)
    for display. The real fix belongs upstream in the seed/ingestion tz handling
    (tracked tech-debt), not here.
    """
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=84))
    sql = (
        "select dayofweekiso(timestampadd('hour', 8, scheduled_start)) as dow, "
        "hour(timestampadd('hour', 8, scheduled_start)) as hour, "
        "count(*) as appointment_count, "
        "count_if(appointment_status = 'completed') as completed_count "
        f"from {fq('stg', 'stg_nextech__appointments', tenant)} "
        "where timestampadd('hour', 8, scheduled_start)::date between %s and %s "
        "group by 1, 2 order by 1, 2"
    )
    return fetch_models(cur, sql, (start, end), FlowByHourRow)


@router.get("/flow/no-show-by-provider", response_model=list[NoShowByProviderRow])
def no_show_by_provider(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[NoShowByProviderRow]:
    """No-show / cancel rates per provider, from int_appointment_disposition
    (the only grain that carries per-provider dispositions)."""
    sql = (
        "select d.provider_id, p.full_name as provider_name, "
        "count(*) as scheduled, "
        "count_if(d.is_completed) as completed, "
        "count_if(d.is_no_show) as no_show, "
        "count_if(d.is_cancelled) as cancelled, "
        "count_if(d.is_no_show) / nullif(count(*), 0) as no_show_rate, "
        "count_if(d.is_cancelled) / nullif(count(*), 0) as cancel_rate "
        f"from {fq('int', 'int_appointment_disposition', tenant)} d "
        f"join {fq('stg', 'stg_nextech__providers', tenant)} p on d.provider_id = p.provider_id "
        "group by 1, 2 order by no_show_rate desc nulls last"
    )
    return fetch_models(cur, sql, (), NoShowByProviderRow)


@router.get("/patients/tier-summary", response_model=PatientTierSummary)
def patient_tier_summary(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> PatientTierSummary:
    """Recency-tier counts across non-deleted patients (e.g. for an 'active
    patients' KPI). Sourced from int_patient_lifetime_value."""
    sql = (
        "select count_if(recency_tier = 'active') as active, "
        "count_if(recency_tier = 'lapsing') as lapsing, "
        "count_if(recency_tier = 'lapsed') as lapsed, "
        "count_if(recency_tier = 'dormant') as dormant, "
        "count(*) as total "
        f"from {fq('int', 'int_patient_lifetime_value', tenant)} where not is_deleted"
    )
    return fetch_models(cur, sql, (), PatientTierSummary)[0]
