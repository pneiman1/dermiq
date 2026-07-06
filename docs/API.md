# DermIQ API

FastAPI backend serving the dbt marts to the frontend. All data endpoints live
under `/api/v1` and require an `X-Tenant-ID` header (a stub for real auth — see
[Future work](#future-work)). `/health` is intentionally **unauthenticated** so
infra liveness probes work.

- Run locally: `make api-run` (uvicorn on `:8000`, autoreload). Needs a populated
  `.env` (Snowflake creds) — the Makefile loads it.
- Tests: `make api-test` (hits real Snowflake; skips without credentials).
- Interactive docs: `http://localhost:8000/docs`.

**Money & rates are serialized as JSON strings**, not numbers — they are SQL
`NUMBER`/`Decimal` and we preserve precision. Parse them on the frontend to
Number/BigNumber as needed.

```bash
BASE=http://localhost:8000/api/v1
H='X-Tenant-ID: del_mar'
```

---

## Meta

### `GET /health`
Liveness + a cheap Snowflake reachability probe. **No header required.**
```bash
curl -s $BASE/health
```
```json
{ "status": "ok", "snowflake_reachable": true }
```

### `GET /meta/tenant`
Tenant metadata (gated). Missing/invalid `X-Tenant-ID` → `400`.
```bash
curl -s $BASE/meta/tenant -H "$H"
```
```json
{ "tenant_id": "del_mar", "tenant_name": "Del Mar Cosmetic Dermatology" }
```

---

## Revenue

### `GET /revenue/daily?start_date=&end_date=`
Per-day revenue from `mart_revenue_daily`, sorted `date_day` desc. Defaults to the
last 90 days. Dates are `YYYY-MM-DD`.
```bash
curl -s "$BASE/revenue/daily?start_date=2026-01-01&end_date=2026-06-30" -H "$H"
```
```json
[
  {
    "date_day": "2026-06-10", "completed_visits": 26,
    "net_revenue": "28170.0000", "avg_ticket": "1083.4615",
    "rev_injectable": "16299.0000", "rev_device": "8050.0000",
    "rev_skincare": "3371.0000", "rev_membership": "0.0000",
    "rev_surgical": "400.0000", "rev_consult": "50.0000",
    "line_items": 48, "distinct_patients": 26, "distinct_providers": 7,
    "new_patients": 21, "scheduled_appointments": 28,
    "no_show_count": 1, "cancelled_count": 1, "no_show_rate": "0.0357"
  }
]
```

---

## Providers

### `GET /providers/scorecard`
One row per provider from `mart_provider_scorecard`, sorted `revenue_per_hour_ttm`
desc. TTM-primary metrics with all-time context and a `revenue_rank`.
```bash
curl -s $BASE/providers/scorecard -H "$H"
```
```json
[
  {
    "provider_id": "prov_003", "provider_name": "Sofia Reyes, MD",
    "provider_role": "MD", "specialties": "Dermatology, lasers, devices",
    "visits_ttm": 943, "revenue_ttm": "1105220.2500",
    "avg_ticket_ttm": "1172.0257", "revenue_per_hour_ttm": "1845.8793",
    "cross_sell_rate_ttm": "0.4072", "skincare_attach_rate_ttm": "0.2057",
    "productive_hours_ttm": "598.75", "active_days_ttm": 275,
    "total_visits_alltime": 1017, "total_revenue_alltime": "1187843.5000",
    "last_visit_date": "2026-06-10", "revenue_rank": 1
  }
]
```

### `GET /providers/{provider_id}/revenue-daily?start_date=&end_date=`
Drill-down: per-day metrics for one provider from `int_provider_daily` (a grain
the marts don't expose). Defaults to the last 90 days. Unknown provider → `[]`.
```bash
curl -s "$BASE/providers/prov_001/revenue-daily?start_date=2026-01-01&end_date=2026-06-30" -H "$H"
```
```json
[
  {
    "provider_id": "prov_001", "date_key": "2026-03-27", "visit_count": 5,
    "total_revenue": "3695.0000", "avg_ticket": "739.0000",
    "productive_hours": "2.75", "revenue_per_hour": "1343.6364",
    "cross_sell_rate": "0.0000", "skincare_attach_rate": "0.0000"
  }
]
```

---

## Channels

### `GET /channels/attribution`
One row per acquisition channel from `mart_channel_attribution`, sorted
`patients_acquired_ttm` desc. Includes spend-driven CAC / LTV:CAC / health.
```bash
curl -s $BASE/channels/attribution -H "$H"
```
```json
[
  {
    "acquisition_channel": "google_ads", "patients_acquired_ttm": 664,
    "total_revenue_ttm": "1241424.0000", "avg_ltv_run_rate_ttm": "4030.1532",
    "vip_count": 75, "high_count": 221, "standard_count": 273,
    "low_count": 95, "unknown_count": 0, "total_patients_alltime": 918,
    "spend_ttm": "84000.0000", "cac_ttm": "126.5060",
    "ltv_cac_ratio_ttm": "31.8574", "channel_health": "excellent"
  }
]
```
> `unknown_count` is always 0 here — the TTM cohort is patients whose first visit
> is in the window, which by definition excludes never-visited patients.

### `GET /channels/acquisition-by-month?months=18`
Patient acquisitions by channel by month (long/denormalized — one row per
month × channel), for stacked-bar charts. Derived from `int_patient_lifetime_value`
(`first_visit_date` bucketed by month). `months` ∈ [1, 60], default 18.
```bash
curl -s "$BASE/channels/acquisition-by-month?months=6" -H "$H"
```
```json
[
  { "month_start": "2025-12-01", "channel": "alle_directory", "patient_count": 11 }
]
```

---

## Recall

### `GET /recall/queue?limit=100&min_priority=low`
Top-N patients to recall from `mart_recall_queue`, sorted by `recall_priority`
(urgent > high > medium > low) then `last_visit_date` asc. `min_priority` filters
to that tier and above. `limit` ∈ [1, 5000].

### `GET /recall/summary`
Aggregate of the recall queue — counts by priority, average recency, latest visit
date. (The row endpoint is paginated, so counts live here.)
```bash
curl -s $BASE/recall/summary -H "$H"
```
```json
{ "total": 1099, "urgent": 41, "high": 168, "medium": 612, "low": 278, "avg_recency_days": 281, "max_last_visit_date": "2026-03-11" }
```
```bash
curl -s "$BASE/recall/queue?limit=3&min_priority=urgent" -H "$H"
```
```json
[
  {
    "patient_id": "pat_002720", "first_name": "Selena", "last_name": "Anderson",
    "primary_email": null, "primary_phone": null,
    "acquisition_channel": "referral", "last_visit_date": "2025-10-29",
    "recency_days": 238, "recency_tier": "lapsing",
    "total_visits": 5, "total_revenue": "9080.5000",
    "annual_revenue_run_rate": "9080.5000", "ltv_tier": "vip",
    "last_provider_id": "prov_006", "last_provider_name": "Cassandra Chen, PA-C",
    "recall_priority": "urgent"
  }
]
```

---

## Flow

### `GET /flow/dispositions?start_date=&end_date=`
Per-day appointment dispositions (completed / no-show / cancelled counts + rates)
from `int_appointment_disposition`, for funnel and heatmap views. Defaults to the
last 90 days.
```bash
curl -s "$BASE/flow/dispositions?start_date=2026-01-01&end_date=2026-06-30" -H "$H"
```
```json
[
  {
    "day": "2026-03-27", "completed": 15, "no_show": 0, "cancelled": 0,
    "total": 15, "no_show_rate": "0.000000", "cancel_rate": "0.000000"
  }
]
```

### `GET /flow/by-hour?start_date=&end_date=`
Appointment volume by ISO day-of-week (`dow`: 1=Mon … 7=Sun) × hour-of-day
(`hour`: 0–23), for the day×hour heatmap. Defaults to the trailing 84 days.
Hours are corrected +8h to clinic-local business hours (see code note — the seed
stored naive local times as UTC).
```bash
curl -s $BASE/flow/by-hour -H "$H"
```
```json
[
  { "dow": 1, "hour": 9, "appointment_count": 34, "completed_count": 31 }
]
```

### `GET /flow/no-show-by-provider`
No-show / cancel rates per provider, from `int_appointment_disposition` (the only
grain with per-provider dispositions). Sorted by no-show rate desc.
```bash
curl -s $BASE/flow/no-show-by-provider -H "$H"
```
```json
[
  { "provider_id": "prov_005", "provider_name": "Anita Desai, MD", "scheduled": 812,
    "completed": 740, "no_show": 44, "cancelled": 28,
    "no_show_rate": "0.054187", "cancel_rate": "0.034483" }
]
```

---

## Patients

### `GET /patients/tier-summary`
Recency-tier counts across non-deleted patients (e.g. for an "active patients"
KPI). `total` includes never-visited patients (whose recency tier is null).
```bash
curl -s $BASE/patients/tier-summary -H "$H"
```
```json
{ "active": 612, "lapsing": 388, "lapsed": 1043, "dormant": 1297, "total": 3498 }
```

---

## Segments (patient clustering)

### `GET /segments`
The discovered patient segments (k-means clusters), one row each, ordered by
`avg_ltv` desc.
```bash
curl -s $BASE/segments -H "$H"
```
```json
[
  { "cluster_id": 0, "cluster_name": "Membership — frequent VIP", "patient_count": 57,
    "avg_ltv": "18500.0000", "avg_annual_run_rate": "11533.0000", "dominant_category": "membership",
    "top_provider_name": "Vivian Park, MD", "avg_recency_days": 120,
    "urgent_recall_count": 3, "active_patient_count": 41 }
]
```

### `GET /segments/{cluster_id}/members?limit=50`
Members of one segment, sorted by `total_revenue` desc. `404` if the cluster id
doesn't exist. `limit` ∈ [1, 1000].
```bash
curl -s "$BASE/segments/0/members?limit=50" -H "$H"
```
```json
[
  { "patient_id": "pat_001234", "first_name": "Jane", "last_name": "Doe",
    "total_revenue": "24500.0000", "annual_revenue_run_rate": "12000.0000",
    "ltv_tier": "vip", "recency_tier": "active", "last_visit_date": "2026-05-30",
    "dominant_provider_name": "Vivian Park, MD" }
]
```

---

## Errors

| Status | When |
|---|---|
| `400` | `X-Tenant-ID` missing or not a known tenant (all endpoints except `/health`) |
| `422` | Invalid query param (bad date, out-of-range `months`/`limit`, bad `min_priority`) |
| `500` | Warehouse query error — safe message returned, full error logged via structlog |

---

## Future work

1. **Connection pooling.** The app holds a *single* long-lived Snowflake
   connection (opened at startup, a fresh cursor per request). To stop the session
   token expiring overnight, `client_session_keep_alive=True` is enabled on the
   connection (platform-core `get_snowflake_connection`) — its background heartbeat
   auto-refreshes the token. **This is the dev solution (option A).** For real
   concurrent load, migrate to a per-request connection factory (B) or a real pool
   — snowflake-connector pooling / a pooled SQLAlchemy engine with `NullPool` (C).
   If keep-alive proves unreliable in longer running, escalate to B.
2. **Real auth.** `X-Tenant-ID` is a stub. Real auth (Clerk / Auth0 / Cognito —
   TBD) will resolve the tenant from a verified JWT. The handler interface is
   stable: the `current_tenant` dependency keeps returning a `tenant_id`; only its
   source changes (header → token claim).
3. **Decimal serialization contract.** Money/rates are emitted as JSON **strings**
   to preserve precision. The frontend must parse them (Number for display,
   BigNumber/decimal.js where exactness matters — e.g. summing revenue client-side).
