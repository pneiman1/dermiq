import os

import pytest

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

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials",
)

TENANT_HEADERS = {"X-Tenant-ID": "del_mar"}

# Bare data paths — used for the missing-header (400) check.
DATA_PATHS = [
    "/api/v1/revenue/daily",
    "/api/v1/providers/scorecard",
    "/api/v1/providers/prov_001/revenue-daily",
    "/api/v1/channels/attribution",
    "/api/v1/channels/acquisition-by-month",
    "/api/v1/recall/queue",
    "/api/v1/flow/dispositions",
    "/api/v1/flow/by-hour",
    "/api/v1/flow/no-show-by-provider",
    "/api/v1/patients/tier-summary",
    "/api/v1/recall/summary",
]

# Path (with wide ranges so date-bounded endpoints are non-empty regardless of
# today's date) + the response row model to validate against.
ENDPOINTS = [
    ("/api/v1/revenue/daily?start_date=2025-01-01&end_date=2026-12-31", RevenueDailyRow),
    ("/api/v1/providers/scorecard", ProviderScorecardRow),
    ("/api/v1/providers/prov_001/revenue-daily?start_date=2025-01-01&end_date=2026-12-31", ProviderRevenueDailyRow),
    ("/api/v1/channels/attribution", ChannelAttributionRow),
    ("/api/v1/channels/acquisition-by-month?months=24", AcquisitionByMonthRow),
    ("/api/v1/recall/queue", RecallQueueRow),
    ("/api/v1/flow/dispositions?start_date=2025-01-01&end_date=2026-12-31", DispositionDailyRow),
    ("/api/v1/flow/by-hour", FlowByHourRow),
    ("/api/v1/flow/no-show-by-provider", NoShowByProviderRow),
]


@pytest.mark.parametrize("path", DATA_PATHS)
def test_missing_tenant_header_400(client, path):
    assert client.get(path).status_code == 400


@pytest.mark.parametrize("path,model", ENDPOINTS)
def test_200_nonempty_and_schema(client, path, model):
    r = client.get(path, headers=TENANT_HEADERS)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) > 0
    # Every row must satisfy the declared response model.
    for row in rows[:50]:
        model.model_validate(row)


def test_patient_tier_summary_200(client):
    r = client.get("/api/v1/patients/tier-summary", headers=TENANT_HEADERS)
    assert r.status_code == 200
    body = r.json()
    PatientTierSummary.model_validate(body)
    assert body["total"] > 0
    assert body["active"] >= 0


def test_recall_summary_200(client):
    r = client.get("/api/v1/recall/summary", headers=TENANT_HEADERS)
    assert r.status_code == 200
    body = r.json()
    RecallSummary.model_validate(body)
    assert body["total"] == body["urgent"] + body["high"] + body["medium"] + body["low"]
