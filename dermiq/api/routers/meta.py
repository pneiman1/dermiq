"""Health and tenant metadata. /health is intentionally unauthenticated so infra
liveness probes work; /meta/tenant is data and is tenant-gated."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from dermiq.api.deps import current_tenant
from dermiq.api.schemas import HealthResponse, TenantResponse

router = APIRouter(tags=["meta"])

TENANT_NAMES = {"del_mar": "Del Mar Cosmetic Dermatology"}


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Liveness + a cheap Snowflake reachability probe. No tenant header required."""
    reachable = True
    try:
        cur = request.app.state.sf_conn.cursor()
        cur.execute("select 1")
        cur.fetchone()
        cur.close()
    except Exception:
        reachable = False
    return HealthResponse(status="ok", snowflake_reachable=reachable)


@router.get("/meta/tenant", response_model=TenantResponse)
def tenant(tenant_id: str = Depends(current_tenant)) -> TenantResponse:
    return TenantResponse(tenant_id=tenant_id, tenant_name=TENANT_NAMES[tenant_id])
