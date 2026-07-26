"""Pydantic response models, one per endpoint, derived from the actual mart/int
columns.

Monetary and rate columns use ``Decimal`` (Snowflake returns ``decimal.Decimal``
for NUMBER columns). Pydantic v2 serializes ``Decimal`` to a JSON **string**,
which preserves precision — a hard requirement for a financial dashboard. The
frontend parses these strings to Number/BigNumber as needed. Integer counts are
``int``; division-derived columns are ``Optional`` since they are NULL when the
denominator is zero.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


# ----- meta -----

class HealthResponse(BaseModel):
    status: str
    snowflake_reachable: bool


class TenantResponse(BaseModel):
    tenant_id: str
    tenant_name: str


# ----- revenue -----

class RevenueDailyRow(BaseModel):
    date_day: date
    completed_visits: int
    net_revenue: Decimal
    avg_ticket: Decimal | None
    rev_injectable: Decimal
    rev_device: Decimal
    rev_skincare: Decimal
    rev_membership: Decimal
    rev_surgical: Decimal
    rev_consult: Decimal
    line_items: int
    distinct_patients: int
    distinct_providers: int
    new_patients: int
    scheduled_appointments: int
    no_show_count: int
    cancelled_count: int
    no_show_rate: Decimal | None


# ----- providers -----

class ProviderScorecardRow(BaseModel):
    provider_id: str
    provider_name: str
    provider_role: str
    specialties: str | None
    visits_ttm: int
    revenue_ttm: Decimal
    avg_ticket_ttm: Decimal | None
    revenue_per_hour_ttm: Decimal | None
    cross_sell_rate_ttm: Decimal | None
    skincare_attach_rate_ttm: Decimal | None
    productive_hours_ttm: Decimal
    active_days_ttm: int
    total_visits_alltime: int
    total_revenue_alltime: Decimal
    last_visit_date: date | None
    revenue_rank: int


class ProviderRevenueDailyRow(BaseModel):
    provider_id: str
    date_key: date
    visit_count: int
    total_revenue: Decimal
    avg_ticket: Decimal | None
    productive_hours: Decimal
    revenue_per_hour: Decimal | None
    cross_sell_rate: Decimal | None
    skincare_attach_rate: Decimal | None


# ----- channels -----

class ChannelAttributionRow(BaseModel):
    acquisition_channel: str
    patients_acquired_ttm: int
    total_revenue_ttm: Decimal
    avg_ltv_run_rate_ttm: Decimal | None
    vip_count: int
    high_count: int
    standard_count: int
    low_count: int
    unknown_count: int
    total_patients_alltime: int
    spend_ttm: Decimal
    cac_ttm: Decimal | None
    ltv_cac_ratio_ttm: Decimal | None
    channel_health: str


class AcquisitionByMonthRow(BaseModel):
    month_start: date
    channel: str
    patient_count: int


# ----- recall -----

class RecallQueueRow(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    primary_email: str | None
    primary_phone: str | None
    acquisition_channel: str
    last_visit_date: date
    recency_days: int
    recency_tier: str
    total_visits: int
    total_revenue: Decimal
    annual_revenue_run_rate: Decimal | None
    ltv_tier: str
    last_provider_id: str | None
    last_provider_name: str | None
    recall_priority: str


# ----- flow -----

class DispositionDailyRow(BaseModel):
    day: date
    completed: int
    no_show: int
    cancelled: int
    total: int
    no_show_rate: Decimal | None
    cancel_rate: Decimal | None


class FlowByHourRow(BaseModel):
    dow: int  # ISO day-of-week: 1=Mon … 7=Sun
    hour: int  # 0 … 23
    appointment_count: int
    completed_count: int


class PatientTierSummary(BaseModel):
    """Recency-tier counts across non-deleted patients (active/lapsing/lapsed/
    dormant; total includes never-visited, whose tier is null)."""
    active: int
    lapsing: int
    lapsed: int
    dormant: int
    total: int


class NoShowByProviderRow(BaseModel):
    provider_id: str
    provider_name: str
    scheduled: int
    completed: int
    no_show: int
    cancelled: int
    no_show_rate: Decimal | None
    cancel_rate: Decimal | None


class RecallSummary(BaseModel):
    """Aggregate of the recall queue — counts by priority, plus avg recency and
    the latest visit date. (The row endpoint is paginated, so counts live here.)"""
    total: int
    urgent: int
    high: int
    medium: int
    low: int
    avg_recency_days: int | None
    max_last_visit_date: date | None


class PatientSegment(BaseModel):
    cluster_id: int
    cluster_name: str
    patient_count: int
    avg_ltv: Decimal
    avg_annual_run_rate: Decimal
    dominant_category: str
    top_provider_name: str | None
    avg_recency_days: int | None
    urgent_recall_count: int
    active_patient_count: int


class PatientSegmentMember(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    total_revenue: Decimal
    annual_revenue_run_rate: Decimal | None
    ltv_tier: str
    recency_tier: str | None
    last_visit_date: date | None
    dominant_provider_name: str | None


# ----- chat (RAG) -----

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class ChatSource(BaseModel):
    """A retrieved corpus document surfaced as a citation."""
    title: str
    source: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


# ----- inventory (chunk-11) -----
class TrueMarginRow(BaseModel):
    service_code: str
    service_name: str
    service_category: str
    transactions_ttm: int
    units_consumed_ttm: Decimal
    revenue_ttm: Decimal
    consumables_cost_ttm: Decimal
    true_margin_ttm: Decimal
    true_margin_pct: Decimal | None
    catalog_margin_pct: Decimal | None


class InventoryStatusRow(BaseModel):
    sku: str
    sku_name: str
    service_code: str
    category: str
    unit_of_measure: str
    on_hand_quantity: Decimal
    par_level: Decimal
    unit_cost: Decimal
    on_hand_value: Decimal
    units_consumed_ttm: Decimal
    days_of_supply: Decimal | None
    oldest_lot_expiry: date | None
    last_transaction_at: date | None
    on_hand_lots: str | None
    stock_status: str


class WasteBySkuRow(BaseModel):
    service_code: str
    service_name: str
    category: str
    consumed_units_ttm: Decimal
    waste_units_ttm: Decimal
    waste_cost_ttm: Decimal
    waste_rate: Decimal | None


class ExpiringItem(BaseModel):
    lot_id: str
    sku: str
    sku_name: str
    category: str
    lot_number: str
    expiry_date: date
    days_to_expiry: int
    quantity_remaining: Decimal
    estimated_value_at_risk: Decimal
    urgency_level: str


class InventorySummary(BaseModel):
    total_inventory_value: Decimal
    waste_rate_ttm: Decimal | None
    waste_value_ttm: Decimal
    items_below_par: int
    expiring_30d_count: int
    expiring_30d_value: Decimal
