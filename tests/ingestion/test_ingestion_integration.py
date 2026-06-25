"""Snowflake-gated integration test for ADR-005.

Proves the original chunk-3 failure mode is fixed end to end: a source table whose
date/text columns are entirely NULL still lands in raw with the declared types
(DATE / VARCHAR), not the NUMBER that pandas inference would have produced.

Skipped automatically when no Snowflake credentials are present in the env, so the
default `pytest tests/ingestion/` run stays offline. Run the full path with:

    set -a; . ./.env; set +a
    pytest tests/ingestion/ -m integration -v
"""
import os
from datetime import datetime, timezone

import pandas as pd
import pytest

pytestmark = pytest.mark.integration

requires_snowflake = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials (SNOWFLAKE_ACCOUNT not set)",
)


@requires_snowflake
def test_all_null_columns_keep_declared_types():
    from platform_core.config import get_settings
    from platform_core.warehouse.connection import get_snowflake_connection
    from platform_core.warehouse.load import load_dataframe
    from platform_core.warehouse.schemas import schema_name

    from dermiq.ingestion.source_to_raw import create_raw_table
    from dermiq.ingestion.types import raw_columns

    settings = get_settings()
    database = settings.snowflake_database
    tenant = settings.default_tenant_id
    # Isolated throwaway schema so we never touch real RAW data.
    test_schema = schema_name("raw", tenant) + "__CITEST"

    columns = [c for c, _ in raw_columns("providers")]
    now = pd.Timestamp(datetime.now(timezone.utc))
    # One row; the historically-problematic columns are all NULL.
    row = {c: None for c in columns}
    row.update(
        provider_id="citest_001",
        full_name="CI Test Provider",
        role="MD",
        created_at=now,
        updated_at=now,
        _ingested_at=now,
        _source_table="nextech_source.providers",
    )
    df = pd.DataFrame([row])[columns]

    with get_snowflake_connection(database=database) as conn:
        try:
            conn.cursor().execute(f'CREATE SCHEMA IF NOT EXISTS "{database}"."{test_schema}"')
            create_raw_table(conn, "providers", schema=test_schema, database=database)
            n = load_dataframe(
                conn, df, table="providers", schema=test_schema,
                auto_create_table=False, overwrite=False,
            )
            assert n == 1

            cur = conn.cursor()
            cur.execute(
                "select column_name, data_type "
                f"from {database}.information_schema.columns "
                f"where table_schema = '{test_schema}' and table_name = 'PROVIDERS'"
            )
            types = {name: dtype for name, dtype in cur.fetchall()}
        finally:
            conn.cursor().execute(f'DROP SCHEMA IF EXISTS "{database}"."{test_schema}"')

    # Snowflake reports VARCHAR as TEXT in INFORMATION_SCHEMA.
    assert types["HIRE_DATE"] == "DATE"
    assert types["TERMINATION_DATE"] == "DATE"
    assert types["NPI_NUMBER"] == "TEXT"
