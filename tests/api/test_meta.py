import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials",
)

TENANT_HEADERS = {"X-Tenant-ID": "del_mar"}


def test_health_needs_no_header_and_reports_reachable(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["snowflake_reachable"] is True


def test_tenant_missing_header_400(client):
    assert client.get("/api/v1/meta/tenant").status_code == 400


def test_tenant_wrong_header_400(client):
    assert client.get("/api/v1/meta/tenant", headers={"X-Tenant-ID": "nope"}).status_code == 400


def test_tenant_with_header_200(client):
    r = client.get("/api/v1/meta/tenant", headers=TENANT_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "del_mar"
    assert body["tenant_name"] == "Del Mar Cosmetic Dermatology"
