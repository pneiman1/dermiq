"""Curated schema of queryable marts for Canvas (chunk-12).

Hand-written (not derived from dbt) so each column carries an LLM-friendly
description and a dimension/measure kind — the model composes chart specs against
this, and the query layer validates against it. Measures carry an aggregation
hint (`sum` vs `avg`) so pre-aggregated and row-level marts both resolve correctly.

Column names are UPPERCASE to match Snowflake; the API/LLM use lowercase and we
match case-insensitively.
"""
from __future__ import annotations

from typing import Any, Literal

Kind = Literal["dimension", "measure"]


def _dim(name: str, desc: str, samples: list[str] | None = None, time: bool = False) -> dict:
    return {"name": name, "type": "date" if time else "string", "kind": "dimension",
            "description": desc, "is_time": time, "sample_values": samples or []}


def _measure(name: str, desc: str, agg: Literal["sum", "avg"] = "sum") -> dict:
    return {"name": name, "type": "number", "kind": "measure", "description": desc, "agg": agg}


# Each mart: fully-qualified layer + table, description, columns.
MARTS: dict[str, dict[str, Any]] = {
    "mart_revenue_daily": {
        "layer": "mart", "grain": "one row per calendar day",
        "description": "Daily practice revenue, category split, volume, and appointment funnel.",
        "columns": [
            _dim("date_day", "Calendar day.", time=True),
            _measure("completed_visits", "Completed visits that day."),
            _measure("net_revenue", "Net revenue (after discounts)."),
            _measure("avg_ticket", "Average revenue per visit.", "avg"),
            _measure("rev_injectable", "Revenue from injectables."),
            _measure("rev_device", "Revenue from energy devices."),
            _measure("rev_skincare", "Revenue from skincare/retail."),
            _measure("rev_membership", "Revenue from memberships."),
            _measure("rev_surgical", "Revenue from surgical."),
            _measure("rev_consult", "Revenue from consults."),
            _measure("new_patients", "New patients acquired that day."),
            _measure("no_show_count", "No-show appointments."),
            _measure("cancelled_count", "Cancelled appointments."),
            _measure("no_show_rate", "No-show rate (0-1).", "avg"),
        ],
    },
    "mart_provider_scorecard": {
        "layer": "mart", "grain": "one row per provider",
        "description": "Per-provider trailing-12-month performance scorecard.",
        "columns": [
            _dim("provider_name", "Provider full name.",
                 ["Marcus Halloway, MD", "Vivian Park, MD", "Sofia Reyes, MD"]),
            _dim("provider_role", "Role.", ["MD", "DO", "PA", "Aesthetician"]),
            _dim("specialties", "Provider specialties (free text)."),
            _measure("visits_ttm", "Visits (TTM)."),
            _measure("revenue_ttm", "Revenue (TTM)."),
            _measure("avg_ticket_ttm", "Average ticket (TTM).", "avg"),
            _measure("revenue_per_hour_ttm", "Revenue per productive hour (TTM).", "avg"),
            _measure("cross_sell_rate_ttm", "Cross-sell rate 0-1 (TTM).", "avg"),
            _measure("skincare_attach_rate_ttm", "Skincare attach rate 0-1 (TTM).", "avg"),
            _measure("productive_hours_ttm", "Productive hours (TTM)."),
            _measure("total_revenue_alltime", "All-time revenue."),
        ],
    },
    "mart_channel_attribution": {
        "layer": "mart", "grain": "one row per acquisition channel",
        "description": "Marketing channel economics (TTM): spend, CAC, LTV:CAC.",
        "columns": [
            _dim("acquisition_channel", "Acquisition channel.",
                 ["google_ads", "instagram_meta", "referral", "realself"]),
            _dim("channel_health", "Health label.",
                 ["organic", "excellent", "healthy", "marginal", "unprofitable"]),
            _measure("patients_acquired_ttm", "Patients acquired (TTM)."),
            _measure("total_revenue_ttm", "Revenue from the channel's cohort (TTM)."),
            _measure("avg_ltv_run_rate_ttm", "Average LTV run-rate (TTM).", "avg"),
            _measure("spend_ttm", "Ad spend (TTM)."),
            _measure("cac_ttm", "Customer acquisition cost (TTM).", "avg"),
            _measure("ltv_cac_ratio_ttm", "LTV:CAC ratio (TTM).", "avg"),
        ],
    },
    "mart_recall_queue": {
        "layer": "mart", "grain": "one row per lapsing patient",
        "description": "Patients due for recall, with recency, priority, and revenue at risk.",
        "columns": [
            _dim("recall_priority", "Priority.", ["urgent", "high", "medium", "low"]),
            _dim("recency_tier", "Recency tier.", ["active", "lapsing", "lapsed", "dormant"]),
            _dim("ltv_tier", "LTV tier.", ["vip", "high", "standard", "low"]),
            _dim("acquisition_channel", "Acquisition channel."),
            _dim("last_provider_name", "Most recent provider."),
            _measure("recency_days", "Days since last visit.", "avg"),
            _measure("total_visits", "Lifetime visits."),
            _measure("total_revenue", "Lifetime revenue."),
            _measure("annual_revenue_run_rate", "Annualized revenue run-rate."),
        ],
    },
    "mart_patient_segments": {
        "layer": "mart", "grain": "one row per patient segment (cluster)",
        "description": "Unsupervised patient segments with size and value profile.",
        "columns": [
            _dim("cluster_name", "Segment name.",
                 ["Injectable VIPs", "Membership VIPs", "Injectable — regulars"]),
            _dim("dominant_category", "Dominant service category."),
            _dim("top_provider_name", "Top provider for the segment."),
            _measure("patient_count", "Patients in the segment."),
            _measure("avg_ltv", "Average lifetime value.", "avg"),
            _measure("avg_annual_run_rate", "Average annual run-rate.", "avg"),
            _measure("urgent_recall_count", "Patients needing urgent recall."),
            _measure("active_patient_count", "Active patients in the segment."),
        ],
    },
    "mart_patient_segment_members": {
        "layer": "mart", "grain": "one row per patient (with segment)",
        "description": "Individual patients mapped to their segment.",
        "columns": [
            _dim("cluster_name", "Segment name."),
            _dim("ltv_tier", "LTV tier.", ["vip", "high", "standard", "low"]),
            _dim("recency_tier", "Recency tier."),
            _dim("dominant_provider_name", "Patient's dominant provider."),
            _measure("total_revenue", "Lifetime revenue."),
            _measure("annual_revenue_run_rate", "Annualized run-rate."),
        ],
    },
    "mart_inventory_status": {
        "layer": "mart", "grain": "one row per consumable SKU",
        "description": "On-hand stock vs par, value, days of supply, and status per SKU.",
        "columns": [
            _dim("sku_name", "Consumable product name."),
            _dim("category", "Category.", ["injectable", "energy_device", "skincare_retail"]),
            _dim("stock_status", "Status.", ["out", "low", "adequate", "overstock"]),
            _measure("on_hand_quantity", "Units on hand."),
            _measure("par_level", "Par level (reorder floor).", "avg"),
            _measure("unit_cost", "Cost per unit.", "avg"),
            _measure("on_hand_value", "On-hand inventory value."),
            _measure("units_consumed_ttm", "Units consumed (TTM)."),
            _measure("days_of_supply", "Days of supply at current run-rate.", "avg"),
        ],
    },
    "mart_true_margin_by_service": {
        "layer": "mart", "grain": "one row per consumable service",
        "description": "True margin (revenue minus real consumables cost) vs catalog margin, per service.",
        "columns": [
            _dim("service_name", "Service name.", ["Botox 40 units", "Voluma 1 syringe"]),
            _dim("service_category", "Category.", ["injectable", "energy_device", "skincare_retail"]),
            _measure("transactions_ttm", "Transactions (TTM)."),
            _measure("revenue_ttm", "Revenue (TTM)."),
            _measure("consumables_cost_ttm", "Real consumables cost (TTM)."),
            _measure("true_margin_ttm", "True margin dollars (TTM)."),
            _measure("true_margin_pct", "True margin as a fraction of revenue.", "avg"),
            _measure("catalog_margin_pct", "Catalog (list-price) margin fraction.", "avg"),
        ],
    },
    "mart_expiring_soon": {
        "layer": "mart", "grain": "one row per on-hand lot near expiry",
        "description": "Inventory lots expiring soon, with days-to-expiry and value at risk.",
        "columns": [
            _dim("sku_name", "Consumable product name."),
            _dim("category", "Category."),
            _dim("urgency_level", "Urgency.", ["critical", "warning", "watch", "future"]),
            _measure("days_to_expiry", "Days until the lot expires.", "avg"),
            _measure("quantity_remaining", "Units remaining in the lot."),
            _measure("estimated_value_at_risk", "Value of the remaining stock."),
        ],
    },
    "int_visit_economics": {
        "layer": "int", "grain": "one row per completed visit",
        "description": "Visit-level economics — good for scatter/line at the visit grain.",
        "columns": [
            _dim("provider_id", "Provider id."),
            _dim("visit_date", "Visit date.", time=True),
            _measure("net_revenue", "Net revenue for the visit."),
            _measure("line_item_count", "Line items on the visit."),
            _measure("actual_duration_min", "Visit duration (minutes).", "avg"),
        ],
    },
    "int_provider_daily": {
        "layer": "int", "grain": "one row per provider per day",
        "description": "Provider daily productivity — good for per-provider time series.",
        "columns": [
            _dim("provider_id", "Provider id."),
            _dim("date_key", "Day.", time=True),
            _measure("visit_count", "Visits that day."),
            _measure("total_revenue", "Revenue that day."),
            _measure("avg_ticket", "Average ticket.", "avg"),
            _measure("revenue_per_hour", "Revenue per hour.", "avg"),
        ],
    },
}


def column(mart: str, name: str) -> dict | None:
    """Case-insensitive column lookup; None if the mart/column is unknown."""
    m = MARTS.get(mart)
    if not m:
        return None
    for c in m["columns"]:
        if c["name"].lower() == name.lower():
            return c
    return None


def as_prompt_text() -> str:
    """Render the schema for the LLM system prompt."""
    lines: list[str] = []
    for name, m in MARTS.items():
        lines.append(f"\n{name} — {m['description']} ({m['grain']})")
        for c in m["columns"]:
            extra = ""
            if c["kind"] == "dimension" and c.get("sample_values"):
                extra = f" e.g. {', '.join(c['sample_values'][:4])}"
            if c.get("is_time"):
                extra = " (time)" + extra
            lines.append(f"  - {c['name']} [{c['kind']}, {c['type']}]: {c['description']}{extra}")
    return "\n".join(lines)


def as_api_payload() -> list[dict]:
    """Serialize the schema for GET /schema (drops internal agg/is_time flags)."""
    out = []
    for name, m in MARTS.items():
        out.append({
            "name": name,
            "description": m["description"],
            "grain": m["grain"],
            "columns": [
                {"name": c["name"], "type": c["type"], "kind": c["kind"],
                 "description": c["description"],
                 "sample_values": c.get("sample_values", [])}
                for c in m["columns"]
            ],
        })
    return out
