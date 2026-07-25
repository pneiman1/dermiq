"""Explicit Snowflake column types for the raw layer.

The single source of truth for the shape of each ``RAW_<TENANT>`` table. Ingestion
creates raw tables from this map instead of relying on ``write_pandas`` dtype
inference, which lands all-NULL (or incidentally-numeric) source columns with the
wrong type — e.g. an all-NULL ``hire_date`` would become ``NUMBER``, breaking the
``NUMBER -> DATE`` cast in staging. See docs/DECISIONS.md ADR-005.

The maps mirror ``infra/postgres/init/01_schema.sql`` (pg type -> Snowflake type):
TEXT->VARCHAR, NUMERIC(p,s)->NUMBER(p,s), INTEGER->INTEGER, BOOLEAN->BOOLEAN,
DATE->DATE, TIMESTAMPTZ->TIMESTAMP_TZ. Column order matches the source ``SELECT *``
so the loaded DataFrame aligns with the created table.
"""
from __future__ import annotations

# Source columns per table, in source order. Keys are the lowercase source column
# names; ingestion uppercases identifiers at load time (Snowflake's unquoted norm).
RAW_COLUMN_TYPES: dict[str, dict[str, str]] = {
    "providers": {
        "provider_id": "VARCHAR",
        "full_name": "VARCHAR",
        "role": "VARCHAR",
        "npi_number": "VARCHAR",
        "specialties": "VARCHAR",
        "hire_date": "DATE",
        "termination_date": "DATE",
        "created_at": "TIMESTAMP_TZ",
        "updated_at": "TIMESTAMP_TZ",
    },
    "services": {
        "service_code": "VARCHAR",
        "service_name": "VARCHAR",
        "category": "VARCHAR",
        "default_price": "NUMBER(10, 2)",
        "default_cost": "NUMBER(10, 2)",
        "typical_duration_min": "INTEGER",
        "active": "BOOLEAN",
        "created_at": "TIMESTAMP_TZ",
        "updated_at": "TIMESTAMP_TZ",
    },
    "patients": {
        "patient_id": "VARCHAR",
        "first_name": "VARCHAR",
        "last_name": "VARCHAR",
        "date_of_birth": "DATE",
        "gender": "VARCHAR",
        "address_zip": "VARCHAR",
        "primary_phone": "VARCHAR",
        "primary_email": "VARCHAR",
        "source_channel": "VARCHAR",
        "created_at": "TIMESTAMP_TZ",
        "updated_at": "TIMESTAMP_TZ",
        "deleted_at": "TIMESTAMP_TZ",
    },
    "appointments": {
        "appointment_id": "VARCHAR",
        "patient_id": "VARCHAR",
        "provider_id": "VARCHAR",
        "appointment_type": "VARCHAR",
        "scheduled_start": "TIMESTAMP_TZ",
        "scheduled_end": "TIMESTAMP_TZ",
        "actual_arrival": "TIMESTAMP_TZ",
        "actual_departure": "TIMESTAMP_TZ",
        "status": "VARCHAR",
        "booking_lead_time_hours": "INTEGER",
        "created_at": "TIMESTAMP_TZ",
        "updated_at": "TIMESTAMP_TZ",
    },
    "transactions": {
        "transaction_id": "VARCHAR",
        "patient_id": "VARCHAR",
        "appointment_id": "VARCHAR",
        "provider_id": "VARCHAR",
        "service_code": "VARCHAR",
        "service_category": "VARCHAR",
        "gross_amount": "NUMBER(10, 2)",
        "discount_amount": "NUMBER(10, 2)",
        "net_amount": "NUMBER(10, 2)",
        "alle_redemption_units": "INTEGER",
        "payment_method": "VARCHAR",
        "transaction_date": "DATE",
        "created_at": "TIMESTAMP_TZ",
    },
    # chunk-11 inventory/consumables. Source precisions intentionally vary
    # (NUMBER(20,4), NUMBER(38,4)) vs services.default_cost NUMBER(10,2); staging
    # normalizes every monetary column to NUMBER(18,4). See docs/DECISIONS.md ADR-010.
    "inventory_units": {
        "unit_id": "VARCHAR",
        "product_name": "VARCHAR",
        "category": "VARCHAR",
        "unit_of_measure": "VARCHAR",
        "service_code": "VARCHAR",
        "units_per_service": "NUMBER(12, 4)",
        "unit_cost": "NUMBER(20, 4)",
        "shelf_life_months": "INTEGER",
        "par_level": "NUMBER(12, 4)",
        "created_at": "TIMESTAMP_TZ",
        "updated_at": "TIMESTAMP_TZ",
    },
    "inventory_lots": {
        "lot_id": "VARCHAR",
        "sku": "VARCHAR",
        "lot_number": "VARCHAR",
        "received_quantity": "NUMBER(12, 4)",
        "received_date": "DATE",
        "expiry_date": "DATE",
        "unit_cost_actual": "NUMBER(20, 4)",
        "created_at": "TIMESTAMP_TZ",
    },
    "inventory_transactions": {
        "inventory_transaction_id": "VARCHAR",
        "transaction_id": "VARCHAR",
        "service_code": "VARCHAR",
        "unit_id": "VARCHAR",
        "lot_id": "VARCHAR",
        "movement_type": "VARCHAR",
        "quantity": "NUMBER(12, 4)",
        "unit_cost": "NUMBER(20, 4)",
        "transaction_value": "NUMBER(38, 4)",
        "consumed_date": "DATE",
        "created_at": "TIMESTAMP_TZ",
    },
    "inventory_current_stock": {
        "sku": "VARCHAR",
        "on_hand_quantity": "NUMBER(18, 4)",
        "oldest_lot_expiry": "DATE",
        "on_hand_lots": "VARCHAR",
        "last_transaction_at": "DATE",
        "created_at": "TIMESTAMP_TZ",
    },
}

# Lineage columns ingestion appends to every raw table (see source_to_raw).
LINEAGE_COLUMN_TYPES: dict[str, str] = {
    "_ingested_at": "TIMESTAMP_TZ",
    "_source_table": "VARCHAR",
}


def raw_columns(table: str) -> list[tuple[str, str]]:
    """Return ``[(column, snowflake_type), ...]`` for a raw table, in load order.

    Source columns first (in source order), then the lineage columns. Raises
    ``KeyError`` for an unknown table so a typo fails loudly.
    """
    if table not in RAW_COLUMN_TYPES:
        raise KeyError(f"Unknown source table {table!r}; known: {sorted(RAW_COLUMN_TYPES)}")
    cols = list(RAW_COLUMN_TYPES[table].items())
    cols.extend(LINEAGE_COLUMN_TYPES.items())
    return cols


def build_create_table_ddl(table: str, *, database: str, schema: str) -> str:
    """Build the ``CREATE OR REPLACE TABLE`` DDL for a raw table from the type map.

    Identifiers are uppercased and quoted; ``CREATE OR REPLACE`` gives full-refresh
    semantics (the table is emptied and re-typed each run).
    """
    column_defs = ",\n".join(
        f'    "{name.upper()}" {sftype}' for name, sftype in raw_columns(table)
    )
    fqn = f'"{database}"."{schema.upper()}"."{table.upper()}"'
    return f"CREATE OR REPLACE TABLE {fqn} (\n{column_defs}\n)"
