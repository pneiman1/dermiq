"""Load the inventory / consumables lifecycle into the Postgres source DB (chunk-11).

Additive: reads the sales transactions already in ``nextech_source`` and builds
the full inventory lifecycle around them — product master, received lots, FIFO
consumption/waste/expiry movements, and derived on-hand stock. It does not touch
providers/services/patients/appointments/transactions, so every existing
downstream mart is unaffected. Safe to re-run — it (re)creates and reloads only
the inventory tables, deterministically.

Run after scripts/seed_postgres.py has populated transactions.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

from platform_core.utils.logging import configure_logging, get_logger

from dermiq.seed.inventory import generate_inventory

log = get_logger(__name__)

POSTGRES_URL = os.environ.get(
    "POSTGRES_SOURCE_URL",
    "postgresql://dermiq:dermiq_local_only@localhost:5432/del_mar_source",
)

_DDL_PATH = Path(__file__).resolve().parents[1] / "infra" / "postgres" / "init" / "02_inventory.sql"


def _apply_schema(cur) -> None:
    """(Re)create the inventory tables so the schema is always in sync."""
    log.info("apply_inventory_schema")
    cur.execute(_DDL_PATH.read_text())


def _load_units(cur, units) -> int:
    rows = [
        (u.unit_id, u.product_name, u.category, u.unit_of_measure, u.service_code,
         u.units_per_service, u.unit_cost, u.shelf_life_months, u.par_level)
        for u in units
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.inventory_units
           (unit_id, product_name, category, unit_of_measure, service_code,
            units_per_service, unit_cost, shelf_life_months, par_level)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        rows, page_size=200,
    )
    return len(rows)


def _load_lots(cur, lots) -> int:
    rows = [
        (l.lot_id, l.sku, l.lot_number, l.received_quantity, l.received_date,
         l.expiry_date, l.unit_cost_actual)
        for l in lots
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.inventory_lots
           (lot_id, sku, lot_number, received_quantity, received_date,
            expiry_date, unit_cost_actual)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        rows, page_size=1000,
    )
    return len(rows)


def _load_movements(cur, movements) -> int:
    rows = [
        (m.inventory_transaction_id, m.transaction_id, m.service_code, m.unit_id,
         m.lot_id, m.movement_type, m.quantity, m.unit_cost, m.transaction_value,
         m.consumed_date)
        for m in movements
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.inventory_transactions
           (inventory_transaction_id, transaction_id, service_code, unit_id,
            lot_id, movement_type, quantity, unit_cost, transaction_value,
            consumed_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        rows, page_size=1000,
    )
    return len(rows)


def _load_current_stock(cur, stock) -> int:
    rows = [
        (s.sku, s.on_hand_quantity, s.oldest_lot_expiry, s.on_hand_lots,
         s.last_transaction_at)
        for s in stock
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.inventory_current_stock
           (sku, on_hand_quantity, oldest_lot_expiry, on_hand_lots, last_transaction_at)
           VALUES (%s, %s, %s, %s, %s)""",
        rows, page_size=200,
    )
    return len(rows)


def main() -> None:
    configure_logging()
    log.info("seed_inventory_start", url=POSTGRES_URL.split("@")[-1])

    with psycopg2.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            _apply_schema(cur)
            cur.execute(
                "SELECT transaction_id, service_code, transaction_date "
                "FROM nextech_source.transactions"
            )
            txn_rows = cur.fetchall()
            log.info("read_transactions", rows=len(txn_rows))

            units, lots, movements, stock = generate_inventory(txn_rows)

            n_units = _load_units(cur, units)
            n_lots = _load_lots(cur, lots)
            n_mov = _load_movements(cur, movements)
            n_stock = _load_current_stock(cur, stock)
        conn.commit()

    log.info(
        "seed_inventory_complete",
        inventory_units=n_units, inventory_lots=n_lots,
        inventory_transactions=n_mov, current_stock=n_stock,
        sales_transactions_seen=len(txn_rows),
    )
    print("\n=== Inventory lifecycle loaded ===")
    print(f"  inventory_units        : {n_units:,}")
    print(f"  inventory_lots         : {n_lots:,}")
    print(f"  inventory_transactions : {n_mov:,}  (consumption / waste / expiry)")
    print(f"  current_stock rows     : {n_stock:,}")
    print(f"  (from {len(txn_rows):,} sales transactions)")
    print()


if __name__ == "__main__":
    main()
