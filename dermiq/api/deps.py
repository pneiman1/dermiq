"""FastAPI dependencies: tenant resolution, per-request cursor, query helper."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel
from snowflake.connector.cursor import SnowflakeCursor

from platform_core.utils.logging import get_logger

log = get_logger(__name__)

# The only tenant for now. Real auth (chunk later) will resolve this from a JWT
# instead of a header; the handler interface ("you get a tenant_id") is stable.
KNOWN_TENANTS = {"del_mar"}


def current_tenant(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> str:
    """Resolve the tenant from the X-Tenant-ID header (stub for real auth).

    Returns the tenant id, or raises 400 if the header is missing or unknown.
    """
    if x_tenant_id is None or x_tenant_id not in KNOWN_TENANTS:
        raise HTTPException(status_code=400, detail="missing or invalid X-Tenant-ID header")
    return x_tenant_id


def db_cursor(request: Request) -> Iterator[SnowflakeCursor]:
    """Yield a fresh cursor off the shared startup connection; close it after.

    Reuses the single long-lived connection on ``app.state`` (created in the
    lifespan handler) rather than opening one per request.
    """
    cur = request.app.state.sf_conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def fetch_models(
    cur: SnowflakeCursor,
    sql: str,
    params: tuple,
    model: type[BaseModel],
) -> list[BaseModel]:
    """Run a query and map each row to ``model`` by lowercased column name.

    Wraps warehouse errors in a 500 with a safe message; logs the full error.
    """
    try:
        cur.execute(sql, params)
        columns = [d[0].lower() for d in cur.description]
        return [model(**dict(zip(columns, row))) for row in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001 — surface as 500, log detail
        log.error("warehouse_query_failed", error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail="internal error querying warehouse")


# Re-exported so routers can write `Depends(current_tenant)` / `Depends(db_cursor)`.
__all__ = ["current_tenant", "db_cursor", "fetch_models", "Depends"]
