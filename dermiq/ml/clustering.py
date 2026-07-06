"""Unsupervised patient segmentation via k-means over behavioral features.

Pipeline: fetch int_patient_features from Snowflake → scale → KMeans(k=7) →
auto-label clusters from their centroids → write per-patient assignments back to
Snowflake (INT_PATIENT_CLUSTER_ASSIGNMENTS). See docs/DECISIONS.md ADR-007.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from snowflake.connector import SnowflakeConnection

from platform_core.config import get_settings
from platform_core.utils.logging import get_logger
from platform_core.warehouse.load import load_dataframe
from platform_core.warehouse.schemas import schema_name

log = get_logger(__name__)

ASSIGNMENTS_TABLE = "int_patient_cluster_assignments"

# Numeric behavioral features fed to k-means (ids / categoricals excluded).
FEATURE_COLS = [
    "total_visits",
    "total_revenue",
    "annual_revenue_run_rate",
    "recency_days",
    "visits_injectable",
    "visits_device",
    "visits_skincare",
    "visits_membership",
    "visits_surgical",
    "visits_consult",
    "rev_injectable_share",
    "rev_device_share",
    "rev_skincare_share",
    "rev_membership_share",
    "rev_surgical_share",
    "rev_consult_share",
    "avg_visits_per_year",
]

# Human-facing base name per dominant service category.
_CATEGORY_BASE = {
    "injectable": "Injectable",
    "energy_device": "Body & device",
    "skincare_retail": "Skincare & facial",
    "membership": "Membership",
    "surgical": "Surgical / vein",
    "consult": "Consult",
}


def fetch_features(conn: SnowflakeConnection, tenant_id: str | None = None) -> pd.DataFrame:
    """Read int_patient_features into a DataFrame (lowercased columns)."""
    settings = get_settings()
    tenant = tenant_id or settings.default_tenant_id
    table = f"{settings.snowflake_database}.{schema_name('int', tenant)}.int_patient_features"
    cur = conn.cursor()
    cur.execute(f"select * from {table}")
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    log.info("fetch_features", rows=len(df), table=table)
    return df


def build_feature_matrix(df: pd.DataFrame):
    """Select numeric features and standardize them. Returns (X, scaler)."""
    matrix = df[FEATURE_COLS].astype(float).to_numpy()
    scaler = StandardScaler()
    X = scaler.fit_transform(matrix)
    return X, scaler


def fit_kmeans(X, k: int = 7):
    """Fit KMeans (fixed seed). Returns (model, labels, inertia)."""
    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(X)
    return model, labels, float(model.inertia_)


# LTV tiers by annualized value, tuned to this practice's segment spread. Tier
# is the primary differentiator between clusters sharing a dominant category.
_LTV_TIERS = (
    (5000, "vip"),
    (1500, "high"),
    (500, "standard"),
)


def _ltv_tier(avg_ltv: float) -> str:
    for threshold, tier in _LTV_TIERS:
        if avg_ltv >= threshold:
            return tier
    return "low"


def _tier_name(base: str, tier: str) -> str:
    """Intentional-reading segment name from category base + LTV tier."""
    return {
        "vip": f"{base} VIPs",
        "high": f"{base} — high value",
        "standard": f"{base} — regulars",
        "low": f"{base} — occasional",
    }[tier]


def label_clusters(df: pd.DataFrame, labels) -> list[dict]:
    """Summarize + name each cluster from its members' feature averages.

    Names read as intentional segments, not algorithmic output. The primary
    differentiator is LTV tier (vip / high / regulars / occasional), so clusters
    sharing a dominant category — e.g. the three injectable cohorts — get distinct
    names ("Injectable VIPs" vs "Injectable — high value" vs "Injectable —
    regulars") without repeating the category.

    If two clusters share both category *and* tier, we escalate on the secondary
    differentiator: recency profile (active vs lapsing), then a numeric suffix as
    a last resort. Provider-based disambiguation is deferred — the feature matrix
    carries only provider_id, not a display name.

    Returns one dict per cluster: cluster_id, cluster_name, cluster_size, avg_ltv,
    dominant_category, sample_patient_ids.
    """
    tagged = df.assign(cluster=labels)
    results: list[dict] = []
    for cid in sorted(tagged["cluster"].unique()):
        members = tagged[tagged["cluster"] == cid]
        dominant_category = members["dominant_category"].mode().iloc[0]
        # Tier on lifetime revenue (matches the mart's avg_ltv), not run-rate.
        avg_ltv = float(members["total_revenue"].mean())
        base = _CATEGORY_BASE.get(dominant_category, dominant_category)
        results.append(
            {
                "cluster_id": int(cid),
                "cluster_name": _tier_name(base, _ltv_tier(avg_ltv)),
                "cluster_size": int(len(members)),
                "avg_ltv": round(avg_ltv, 2),
                "dominant_category": dominant_category,
                "recency_days": float(members["recency_days"].median()),
                "sample_patient_ids": members["patient_id"].head(5).tolist(),
            }
        )

    _disambiguate(results)
    for r in results:
        r.pop("recency_days", None)
    return results


def _disambiguate(results: list[dict]) -> None:
    """Make names unique when category + LTV tier collide (mutates in place)."""
    from collections import defaultdict

    by_name: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_name[r["cluster_name"]].append(r)

    for name, group in by_name.items():
        if len(group) == 1:
            continue
        # Secondary differentiator: recency profile.
        for r in group:
            profile = "active" if r["recency_days"] <= 90 else "lapsing"
            r["cluster_name"] = f"{name} · {profile}"
        # Last resort: numeric suffix on anything still colliding.
        still: dict[str, list[dict]] = defaultdict(list)
        for r in group:
            still[r["cluster_name"]].append(r)
        for nm, sub in still.items():
            if len(sub) == 1:
                continue
            for i, r in enumerate(sorted(sub, key=lambda x: -x["avg_ltv"]), start=1):
                r["cluster_name"] = f"{nm} ({i})"


def write_segments_to_snowflake(
    conn: SnowflakeConnection,
    df: pd.DataFrame,
    labels,
    clusters: list[dict],
    tenant_id: str | None = None,
) -> int:
    """Full-refresh the per-patient cluster assignments table in Snowflake."""
    settings = get_settings()
    tenant = tenant_id or settings.default_tenant_id
    name_by_id = {c["cluster_id"]: c["cluster_name"] for c in clusters}

    assignments = pd.DataFrame(
        {
            "patient_id": df["patient_id"].to_numpy(),
            "cluster_id": [int(x) for x in labels],
            "cluster_name": [name_by_id[int(x)] for x in labels],
            "assigned_at": pd.Timestamp(datetime.now(timezone.utc)),
        }
    )
    n = load_dataframe(
        conn,
        assignments,
        table=ASSIGNMENTS_TABLE,
        schema=schema_name("int", tenant),
        overwrite=True,
    )
    log.info("write_segments", table=ASSIGNMENTS_TABLE, rows=n)
    return n
