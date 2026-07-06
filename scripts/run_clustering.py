"""Run patient clustering: fetch features → KMeans → auto-label → write to Snowflake.

    python scripts/run_clustering.py

Writes INT_DEL_MAR.INT_PATIENT_CLUSTER_ASSIGNMENTS (one row per patient), which the
mart_patient_segments model reads. See docs/DECISIONS.md ADR-010.
"""
from __future__ import annotations

from platform_core.config import get_settings
from platform_core.utils.logging import configure_logging, get_logger
from platform_core.warehouse.connection import get_snowflake_connection

from dermiq.ml.clustering import (
    build_feature_matrix,
    fetch_features,
    fit_kmeans,
    label_clusters,
    write_segments_to_snowflake,
)

log = get_logger(__name__)

# k=7: we baked ~7 personas into the seed data. Real deployments should choose k
# via elbow / silhouette scoring — tracked as tech-debt in ADR-010.
K = 7


def main() -> None:
    configure_logging()
    settings = get_settings()

    with get_snowflake_connection(database=settings.snowflake_database) as conn:
        df = fetch_features(conn)
        X, _scaler = build_feature_matrix(df)
        _model, labels, inertia = fit_kmeans(X, k=K)
        clusters = label_clusters(df, labels)
        written = write_segments_to_snowflake(conn, df, labels, clusters)

    log.info("clustering_complete", patients=len(df), k=K, inertia=round(inertia, 1), written=written)

    print(f"\n=== Patient segments (k={K}, {len(df):,} patients, inertia={inertia:,.0f}) ===")
    for c in sorted(clusters, key=lambda x: -x["cluster_size"]):
        print(
            f"  [{c['cluster_id']}] {c['cluster_name']:<34} "
            f"n={c['cluster_size']:>4}  avg_ltv=${c['avg_ltv']:>11,.0f}  "
            f"dominant={c['dominant_category']}"
        )
    print()


if __name__ == "__main__":
    main()
