"""Patient-segment endpoints (k-means clusters surfaced in AI Studio)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from snowflake.connector.cursor import SnowflakeCursor

from dermiq.api.deps import current_tenant, db_cursor, fetch_models
from dermiq.api.fqn import fq
from dermiq.api.schemas import PatientSegment, PatientSegmentMember

router = APIRouter(tags=["segments"])


@router.get("/segments", response_model=list[PatientSegment])
def segments(
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
) -> list[PatientSegment]:
    sql = f"select * from {fq('mart', 'mart_patient_segments', tenant)} order by avg_ltv desc"
    return fetch_models(cur, sql, (), PatientSegment)


@router.get("/segments/{cluster_id}/members", response_model=list[PatientSegmentMember])
def segment_members(
    cluster_id: int,
    tenant: str = Depends(current_tenant),
    cur: SnowflakeCursor = Depends(db_cursor),
    limit: int = Query(50, ge=1, le=1000),
) -> list[PatientSegmentMember]:
    # 404 if the cluster doesn't exist.
    cur.execute(
        f"select count(*) from {fq('mart', 'mart_patient_segments', tenant)} where cluster_id = %s",
        (cluster_id,),
    )
    if cur.fetchone()[0] == 0:
        raise HTTPException(status_code=404, detail=f"segment {cluster_id} not found")

    sql = (
        f"select * from {fq('mart', 'mart_patient_segment_members', tenant)} "
        "where cluster_id = %s order by total_revenue desc limit %s"
    )
    return fetch_models(cur, sql, (cluster_id, limit), PatientSegmentMember)
