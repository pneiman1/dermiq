"""Unit tests for the explicit raw column-type map (ADR-005). No warehouse needed."""
import pytest

from dermiq.ingestion.types import (
    LINEAGE_COLUMN_TYPES,
    RAW_COLUMN_TYPES,
    build_create_table_ddl,
    raw_columns,
)


def test_all_five_source_tables_mapped():
    assert set(RAW_COLUMN_TYPES) == {
        "providers", "services", "patients", "appointments", "transactions",
    }


def test_raw_columns_appends_lineage_in_order():
    cols = raw_columns("providers")
    names = [c for c, _ in cols]
    # source columns first, in source order...
    assert names[0] == "provider_id"
    assert set(RAW_COLUMN_TYPES["providers"]).issubset(names)
    # ...then the lineage columns, last.
    assert names[-2:] == list(LINEAGE_COLUMN_TYPES)


def test_build_ddl_uses_explicit_types_not_inference():
    ddl = build_create_table_ddl("providers", database="DB", schema="raw_del_mar")
    assert ddl.startswith('CREATE OR REPLACE TABLE "DB"."RAW_DEL_MAR"."PROVIDERS" (')
    # The exact chunk-3 failure columns now get explicit, correct types.
    assert '"NPI_NUMBER" VARCHAR' in ddl
    assert '"HIRE_DATE" DATE' in ddl
    assert '"TERMINATION_DATE" DATE' in ddl
    # Lineage columns are part of the created table.
    assert '"_INGESTED_AT" TIMESTAMP_TZ' in ddl
    assert '"_SOURCE_TABLE" VARCHAR' in ddl


def test_money_and_integer_types_preserved():
    ddl = build_create_table_ddl("transactions", database="D", schema="RAW")
    assert '"GROSS_AMOUNT" NUMBER(10, 2)' in ddl
    assert '"ALLE_REDEMPTION_UNITS" INTEGER' in ddl
    assert '"TRANSACTION_DATE" DATE' in ddl


def test_unknown_table_raises():
    with pytest.raises(KeyError):
        raw_columns("not_a_table")
