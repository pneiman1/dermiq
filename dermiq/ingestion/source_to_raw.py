"""Ingest the Nextech-shaped Postgres source into the Snowflake raw layer.

Reads each table in the ``nextech_source`` schema (via the read-only
``dermiq_reader`` role) and lands a faithful copy in
``<SNOWFLAKE_DATABASE>.RAW_<TENANT>``, adding ingestion-metadata columns.

Full-refresh semantics: each run replaces the raw tables with the current source
snapshot. This is the seam between the source system and the warehouse — the
production analog reads a clinic's live EMR feed on a schedule.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd
import psycopg2
from snowflake.connector import SnowflakeConnection

from platform_core.config import get_settings
from platform_core.utils.logging import get_logger
from platform_core.warehouse.load import load_dataframe
from platform_core.warehouse.schemas import provision_tenant_schemas, schema_name

from dermiq.ingestion.types import build_create_table_ddl, raw_columns

log = get_logger(__name__)

SOURCE_SCHEMA = "nextech_source"

# Source tables to ingest. Raw load has no foreign keys, so order is cosmetic.
SOURCE_TABLES: tuple[str, ...] = (
    "providers",
    "services",
    "patients",
    "appointments",
    "transactions",
    # chunk-11 inventory / consumables layer.
    "inventory_units",
    "inventory_transactions",
)

# Read via the least-privilege read-only role created in 01_schema.sql. Override
# with POSTGRES_SOURCE_READER_URL; defaults to the docker-compose reader creds.
SOURCE_READER_URL = os.environ.get(
    "POSTGRES_SOURCE_READER_URL",
    "postgresql://dermiq_reader:reader_local_only@localhost:5432/del_mar_source",
)


def read_source_table(
    pg_conn,
    table: str,
    *,
    ingested_at: datetime,
) -> pd.DataFrame:
    """Read one source table into a DataFrame with ingestion-metadata columns."""
    with pg_conn.cursor() as cur:
        cur.execute(f'SELECT * FROM {SOURCE_SCHEMA}."{table}"')
        columns = [desc[0] for desc in cur.description]
        rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=columns)
    # Stamp every row from this run with the same ingestion timestamp + lineage.
    df["_ingested_at"] = pd.Timestamp(ingested_at)
    df["_source_table"] = f"{SOURCE_SCHEMA}.{table}"

    log.info("read_source_table", table=table, rows=len(df))
    return df


def create_raw_table(
    sf_conn: SnowflakeConnection,
    table: str,
    *,
    schema: str,
    database: str,
) -> None:
    """Create (or replace) the raw table with explicit column types from the map.

    Replacing rather than inferring makes the raw schema deterministic regardless
    of the data in any single load (ADR-005).
    """
    ddl = build_create_table_ddl(table, database=database, schema=schema)
    with sf_conn.cursor() as cur:
        cur.execute(ddl)
    log.info("create_raw_table", table=table, schema=schema)


def ingest_source_to_raw(
    sf_conn: SnowflakeConnection,
    *,
    tenant_id: str | None = None,
    source_reader_url: str = SOURCE_READER_URL,
) -> dict[str, int]:
    """Land all source tables in the tenant's RAW schema.

    Provisions the tenant's medallion schemas (idempotent), then full-refreshes
    each source table into ``RAW_<TENANT>``. Returns ``{table: rows_loaded}``.
    """
    settings = get_settings()
    tenant = tenant_id or settings.default_tenant_id
    database = settings.snowflake_database
    provision_tenant_schemas(sf_conn, tenant)
    raw_schema = schema_name("raw", tenant)

    # One timestamp for the whole run, so all raw tables share a load batch.
    ingested_at = datetime.now(timezone.utc)

    counts: dict[str, int] = {}
    with psycopg2.connect(source_reader_url) as pg_conn:
        for table in SOURCE_TABLES:
            df = read_source_table(pg_conn, table, ingested_at=ingested_at)
            # Align to the explicit type map (order + names) so the DataFrame
            # matches the table we create; a missing mapped column fails loudly.
            df = df[[col for col, _ in raw_columns(table)]]
            # Create the typed table, then append — no pandas dtype inference.
            create_raw_table(sf_conn, table, schema=raw_schema, database=database)
            counts[table] = load_dataframe(
                sf_conn,
                df,
                table=table,
                schema=raw_schema,
                auto_create_table=False,
                overwrite=False,
            )

    log.info(
        "ingest_source_to_raw_complete",
        tenant_id=tenant,
        schema=raw_schema,
        counts=counts,
    )
    return counts
