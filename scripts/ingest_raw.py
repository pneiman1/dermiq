"""Ingest the Postgres source database into the Snowflake raw layer.

Entry point for the source -> raw step of the pipeline. Reads every
``nextech_source`` table and lands it in ``<SNOWFLAKE_DATABASE>.RAW_<TENANT>``.

    python scripts/ingest_raw.py

Connection settings come from platform-core's Settings (env / .env). The source
read uses the read-only reader role (see dermiq.ingestion.source_to_raw).
"""
from __future__ import annotations

from platform_core.config import get_settings
from platform_core.utils.logging import configure_logging, get_logger
from platform_core.warehouse.connection import get_snowflake_connection
from platform_core.warehouse.schemas import schema_name

from dermiq.ingestion.source_to_raw import ingest_source_to_raw

log = get_logger(__name__)


def main() -> None:
    configure_logging()
    settings = get_settings()
    tenant = settings.default_tenant_id
    raw_schema = schema_name("raw", tenant)

    log.info(
        "ingest_raw_start",
        tenant_id=tenant,
        target=f"{settings.snowflake_database}.{raw_schema}",
    )

    with get_snowflake_connection(database=settings.snowflake_database) as sf_conn:
        counts = ingest_source_to_raw(sf_conn, tenant_id=tenant)

    total = sum(counts.values())
    print(f"\n=== Loaded source -> {settings.snowflake_database}.{raw_schema} ===")
    for table, n_rows in counts.items():
        print(f"  {table:<14}: {n_rows:,}")
    print(f"  {'TOTAL':<14}: {total:,}\n")


if __name__ == "__main__":
    main()
