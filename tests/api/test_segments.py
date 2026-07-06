import os

import pytest

from dermiq.api.schemas import PatientSegment, PatientSegmentMember

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials",
)

TENANT_HEADERS = {"X-Tenant-ID": "del_mar"}


def test_segments_missing_header_400(client):
    assert client.get("/api/v1/segments").status_code == 400


def test_segments_200_sorted_by_ltv(client):
    r = client.get("/api/v1/segments", headers=TENANT_HEADERS)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 7
    for row in rows:
        PatientSegment.model_validate(row)
    ltvs = [float(x["avg_ltv"]) for x in rows]
    assert ltvs == sorted(ltvs, reverse=True)


def test_segment_members_missing_header_400(client):
    assert client.get("/api/v1/segments/0/members").status_code == 400


def test_segment_members_200(client):
    r = client.get("/api/v1/segments/0/members?limit=10", headers=TENANT_HEADERS)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) > 0
    for row in rows:
        PatientSegmentMember.model_validate(row)


def test_segment_members_404_on_invalid_cluster(client):
    assert client.get("/api/v1/segments/999/members", headers=TENANT_HEADERS).status_code == 404
