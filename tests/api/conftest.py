"""Shared fixtures for API tests. These hit real Snowflake (no mocking), so they
skip when no credentials are present. `make api-test` loads .env, so creds are set."""
import os

import pytest
from fastapi.testclient import TestClient

TENANT_HEADERS = {"X-Tenant-ID": "del_mar"}

requires_snowflake = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials (SNOWFLAKE_ACCOUNT not set)",
)


@pytest.fixture(scope="session")
def client():
    """TestClient with lifespan run once (opens/closes the shared connection)."""
    from dermiq.api.main import app

    with TestClient(app) as test_client:
        yield test_client
