"""Composable Canvas endpoints (chunk-12): schema, chart generation, query
resolution, and canvas persistence. Tenant-gated; parameterized queries only."""
from __future__ import annotations

import json
import uuid

import anthropic
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, TypeAdapter
from snowflake.connector.cursor import SnowflakeCursor

from dermiq.api.deps import current_tenant, db_cursor
from dermiq.api.fqn import fq
from dermiq.canvas import generation
from dermiq.canvas import schema as canvas_schema
from dermiq.canvas.query import SpecError, resolve_and_run
from dermiq.canvas.schemas import ChartSpec

router = APIRouter(tags=["canvas"])

_spec_adapter: TypeAdapter = TypeAdapter(ChartSpec)


class QueryRequest(BaseModel):
    chart_spec: dict


class GenerateRequest(BaseModel):
    prompt: str
    existing_charts: list[dict] | None = None


class SaveRequest(BaseModel):
    title: str
    charts: list[dict]
    layout: list[dict]


@router.get("/schema")
def get_schema(tenant: str = Depends(current_tenant)) -> dict:
    """Curated metadata about the marts Canvas can query."""
    return {"marts": canvas_schema.as_api_payload()}


@router.post("/canvas/query")
def canvas_query(
    body: QueryRequest,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> dict:
    try:
        spec = _spec_adapter.validate_python(body.chart_spec)
        data = resolve_and_run(cur, spec, tenant)
    except SpecError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"data": data}


@router.post("/canvas/generate")
def canvas_generate(
    body: GenerateRequest,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> dict:
    try:
        return generation.generate(cur, body.prompt, body.existing_charts)
    except SpecError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Couldn't build a chart for that request. {exc}",
        )
    except anthropic.APIError as exc:  # upstream LLM 5xx / transport
        raise HTTPException(status_code=503, detail="The visualization service is temporarily unavailable. Please retry.") from exc


@router.post("/canvas")
def save_canvas(
    body: SaveRequest,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> dict:
    canvas_id = uuid.uuid4().hex
    payload = json.dumps({"charts": body.charts, "layout": body.layout})
    table = fq("mart", "canvas_layouts", tenant)
    cur.execute(
        f"insert into {table} (canvas_id, tenant_id, title, layout_json) "
        "select %s, %s, %s, parse_json(%s)",
        (canvas_id, tenant, body.title, payload),
    )
    return {"canvas_id": canvas_id, "title": body.title}


@router.get("/canvas")
def list_canvases(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[dict]:
    table = fq("mart", "canvas_layouts", tenant)
    cur.execute(
        f"select canvas_id, title, created_at, updated_at from {table} "
        "where tenant_id = %s order by updated_at desc",
        (tenant,),
    )
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@router.get("/canvas/{canvas_id}")
def load_canvas(
    canvas_id: str,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> dict:
    table = fq("mart", "canvas_layouts", tenant)
    cur.execute(
        f"select title, layout_json from {table} where canvas_id = %s and tenant_id = %s",
        (canvas_id, tenant),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Canvas not found")
    layout = json.loads(row[1]) if isinstance(row[1], str) else row[1]
    return {"canvas_id": canvas_id, "title": row[0],
            "charts": layout.get("charts", []), "layout": layout.get("layout", [])}


@router.delete("/canvas/{canvas_id}")
def delete_canvas(
    canvas_id: str,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> dict:
    table = fq("mart", "canvas_layouts", tenant)
    cur.execute(
        f"delete from {table} where canvas_id = %s and tenant_id = %s",
        (canvas_id, tenant),
    )
    return {"deleted": canvas_id}
