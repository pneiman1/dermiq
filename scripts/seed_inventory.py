"""Load the inventory / consumables layer into the Postgres source database (chunk-11).

This is *additive*: it reads the sales transactions already present in
``nextech_source`` and attaches consumption events to them. It does not touch
providers/services/patients/appointments/transactions, so every existing
downstream mart is unaffected. Safe to re-run — it truncates only the two
inventory tables and regenerates deterministically.

Run after the main seed (scripts/seed_postgres.py) has populated transactions.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

from platform_core.utils.logging import configure_logging, get_logger

from dermiq.seed.inventory import (
    INVENTORY_UNITS,
    generate_inventory_transactions,
)

log = get_logger(__name__)

POSTGRES_URL = os.environ.get(
    "POSTGRES_SOURCE_URL",
    "postgresql://dermiq:dermiq_local_only@localhost:5432/del_mar_source",
)

# The table DDL lives with the rest of the source schema; run it here so an
# already-running container (where init scripts don't re-run) gets the tables.
_DDL_PATH = Path(__file__).resolve().parents[1] / "infra" / "postgres" / "init" / "02_inventory.sql"


def _ensure_tables(cur) -> None:
    log.info("ensure_inventory_tables")
    cur.execute(_DDL_PATH.read_text())


def _truncate_inventory(cur) -> None:
    log.info("truncate_inventory_tables")
    cur.execute(
        "TRUNCATE TABLE nextech_source.inventory_transactions, "
        "nextech_source.inventory_units RESTART IDENTITY CASCADE"
    )


def _load_units(cur) -> int:
    rows = [
        (
            u.unit_id,
            u.product_name,
            u.category,
            u.unit_of_measure,
            u.service_code,
            u.units_per_service,
            u.unit_cost,
        )
        for u in INVENTORY_UNITS
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.inventory_units
           (unit_id, product_name, category, unit_of_measure, service_code,
            units_per_service, unit_cost)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=200,
    )
    return len(rows)


def _load_inventory_transactions(cur, inv_txns) -> int:
    rows = [
        (
            it.inventory_transaction_id,
            it.transaction_id,
            it.service_code,
            it.unit_id,
            it.quantity,
            it.unit_cost,
            it.transaction_value,
            it.consumed_date,
        )
        for it in inv_txns
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.inventory_transactions
           (inventory_transaction_id, transaction_id, service_code, unit_id,
            quantity, unit_cost, transaction_value, consumed_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=1000,
    )
    return len(rows)


def main() -> None:
    configure_logging()
    log.info("seed_inventory_start", url=POSTGRES_URL.split("@")[-1])

    with psycopg2.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            _ensure_tables(cur)
            # Read the sales transactions we are attaching consumption to.
            cur.execute(
                "SELECT transaction_id, service_code, transaction_date "
                "FROM nextech_source.transactions"
            )
            txn_rows = cur.fetchall()
            log.info("read_transactions", rows=len(txn_rows))

            inv_txns = generate_inventory_transactions(txn_rows)

            _truncate_inventory(cur)
            n_units = _load_units(cur)
            n_inv_txn = _load_inventory_transactions(cur, inv_txns)
        conn.commit()

    log.info(
        "seed_inventory_complete",
        inventory_units=n_units,
        inventory_transactions=n_inv_txn,
        sales_transactions_seen=len(txn_rows),
    )
    print("\n=== Inventory layer loaded ===")
    print(f"  inventory_units        : {n_units:,}")
    print(f"  inventory_transactions : {n_inv_txn:,}")
    print(f"  (from {len(txn_rows):,} sales transactions)")
    print()


if __name__ == "__main__":
    main()
