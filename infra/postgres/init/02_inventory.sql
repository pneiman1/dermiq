-- Inventory / consumables layer for Del Mar Cosmetic Dermatology (chunk-11).
--
-- Models the product cost-of-goods behind each service so we can compute the
-- *true* margin (revenue minus real consumables consumed) rather than the
-- catalog margin (default_price minus default_cost). Injectables burn toxin
-- units and filler syringes; energy devices burn per-treatment consumables;
-- retail moves product. Actual consumption runs a little above the catalog
-- assumption (real acquisition prices + waste), which is the whole point.
--
-- Loaded automatically on first container start via /docker-entrypoint-initdb.d
-- (after 01_schema.sql). For an already-running container, scripts/seed_inventory.py
-- creates these tables if they are missing before loading.

SET search_path TO nextech_source, public;

-- ============ Inventory units (consumable product master) ============
-- One row per consumable a service burns. unit_cost is the real per-unit
-- acquisition cost. Deliberately wider precision than services.default_cost
-- (NUMERIC(10,2)) — staging normalizes every monetary column to NUMBER(18,4).

CREATE TABLE IF NOT EXISTS inventory_units (
    unit_id              TEXT PRIMARY KEY,
    product_name         TEXT NOT NULL,
    category             TEXT NOT NULL,
    unit_of_measure      TEXT NOT NULL,       -- 'unit' | 'syringe' | 'treatment' | 'product'
    service_code         TEXT NOT NULL REFERENCES services (service_code),
    units_per_service    NUMERIC(12, 4) NOT NULL,   -- base quantity consumed per service performed
    unit_cost            NUMERIC(20, 4) NOT NULL,   -- real acquisition cost per unit_of_measure
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inv_units_service ON inventory_units (service_code);

-- ============ Inventory transactions (consumption events) ============
-- One or more rows per sales transaction: what product was consumed to deliver
-- that service, how much, and at what cost. transaction_value = quantity *
-- unit_cost, materialized at the widest precision so the arithmetic never
-- silently truncates before staging casts it down to the NUMBER(18,4) standard.

CREATE TABLE IF NOT EXISTS inventory_transactions (
    inventory_transaction_id  TEXT PRIMARY KEY,
    transaction_id            TEXT NOT NULL REFERENCES transactions (transaction_id),
    service_code              TEXT NOT NULL REFERENCES services (service_code),
    unit_id                   TEXT NOT NULL REFERENCES inventory_units (unit_id),
    quantity                  NUMERIC(12, 4) NOT NULL,
    unit_cost                 NUMERIC(20, 4) NOT NULL,
    transaction_value         NUMERIC(38, 4) NOT NULL,
    consumed_date             DATE NOT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inv_txn_transaction ON inventory_transactions (transaction_id);
CREATE INDEX IF NOT EXISTS idx_inv_txn_service ON inventory_transactions (service_code);
CREATE INDEX IF NOT EXISTS idx_inv_txn_consumed_date ON inventory_transactions (consumed_date);

-- Read-only analytics role (created in 01_schema.sql) needs SELECT on the new tables.
GRANT SELECT ON inventory_units, inventory_transactions TO dermiq_reader;
