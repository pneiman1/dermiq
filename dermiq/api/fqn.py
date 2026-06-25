"""Fully-qualified table names from the platform-core schema convention.

Keeps the API from hardcoding ``MART_DEL_MAR`` etc. — names derive from the tenant
and the medallion layer exactly as ingestion and dbt do.
"""
from __future__ import annotations

from platform_core.config import get_settings
from platform_core.warehouse.schemas import schema_name


def fq(layer: str, table: str, tenant: str) -> str:
    """Return ``<database>.<LAYER>_<TENANT>.<table>`` for a layer/table/tenant."""
    database = get_settings().snowflake_database
    return f"{database}.{schema_name(layer, tenant)}.{table}"
