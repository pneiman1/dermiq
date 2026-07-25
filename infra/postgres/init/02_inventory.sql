-- Inventory / consumables layer for Del Mar Cosmetic Dermatology (chunk-11).
--
-- Full consumables lifecycle behind the Inventory tab: a consumable product
-- master (inventory_units), receiving events (inventory_lots), FIFO draw-down
-- movements (inventory_transactions: consumption / waste / expiry), and derived
-- on-hand stock (inventory_current_stock). Lets us compute true margin (revenue
-- vs real consumables cost), waste, below-par stock, and expiring lots — all from
-- real modeled data rather than list price.
--
-- Loaded automatically on first container start via /docker-entrypoint-initdb.d
-- (after 01_schema.sql). For an already-running container, scripts/seed_inventory.py
-- runs this file before loading. Inventory is fully regenerated each seed run, so
-- the tables are dropped and recreated to keep the schema in sync.

SET search_path TO nextech_source, public;

DROP TABLE IF EXISTS inventory_current_stock CASCADE;
DROP TABLE IF EXISTS inventory_transactions CASCADE;
DROP TABLE IF EXISTS inventory_lots CASCADE;
DROP TABLE IF EXISTS inventory_units CASCADE;

-- ============ Inventory units (consumable product master) ============
-- One row per SKU (consumable) a service burns. unit_cost is the nominal real
-- acquisition cost; par_level drives below-par alerts. Wider precision than
-- services.default_cost (NUMERIC(10,2)) — staging normalizes to NUMBER(18,4).

CREATE TABLE inventory_units (
    unit_id              TEXT PRIMARY KEY,
    product_name         TEXT NOT NULL,
    category             TEXT NOT NULL,
    unit_of_measure      TEXT NOT NULL,       -- 'unit' | 'syringe' | 'treatment' | 'product'
    service_code         TEXT NOT NULL REFERENCES services (service_code),
    units_per_service    NUMERIC(12, 4) NOT NULL,
    unit_cost            NUMERIC(20, 4) NOT NULL,
    shelf_life_months    INTEGER NOT NULL,
    par_level            NUMERIC(12, 4) NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ Inventory lots (receiving events) ============
-- One row per bulk order received. unit_cost_actual varies per lot (real clinics
-- see acquisition-price drift); expiry_date reflects SKU shelf life.

CREATE TABLE inventory_lots (
    lot_id               TEXT PRIMARY KEY,
    sku                  TEXT NOT NULL REFERENCES inventory_units (unit_id),
    lot_number           TEXT NOT NULL,
    received_quantity    NUMERIC(12, 4) NOT NULL,
    received_date        DATE NOT NULL,
    expiry_date          DATE NOT NULL,
    unit_cost_actual     NUMERIC(20, 4) NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inv_lots_sku ON inventory_lots (sku);
CREATE INDEX idx_inv_lots_expiry ON inventory_lots (expiry_date);

-- ============ Inventory transactions (FIFO draw-down movements) ============
-- consumption / waste draw against a lot to deliver a sale (transaction_id set);
-- expiry write-offs have no sale (transaction_id null). lot_id is null only for
-- the rare unallocatable draw. transaction_value = quantity * unit_cost at the
-- widest precision; staging casts it to the NUMBER(18,4) standard.

CREATE TABLE inventory_transactions (
    inventory_transaction_id  TEXT PRIMARY KEY,
    transaction_id            TEXT REFERENCES transactions (transaction_id),
    service_code              TEXT NOT NULL REFERENCES services (service_code),
    unit_id                   TEXT NOT NULL REFERENCES inventory_units (unit_id),
    lot_id                    TEXT REFERENCES inventory_lots (lot_id),
    movement_type             TEXT NOT NULL,   -- 'consumption' | 'waste' | 'expiry'
    quantity                  NUMERIC(12, 4) NOT NULL,
    unit_cost                 NUMERIC(20, 4) NOT NULL,
    transaction_value         NUMERIC(38, 4) NOT NULL,
    consumed_date             DATE NOT NULL,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_inv_txn_transaction ON inventory_transactions (transaction_id);
CREATE INDEX idx_inv_txn_service ON inventory_transactions (service_code);
CREATE INDEX idx_inv_txn_lot ON inventory_transactions (lot_id);
CREATE INDEX idx_inv_txn_type ON inventory_transactions (movement_type);
CREATE INDEX idx_inv_txn_consumed_date ON inventory_transactions (consumed_date);

-- ============ Current stock (derived on-hand position) ============
-- One row per SKU: on-hand quantity today (lots received, minus consumed/waste/
-- expired). on_hand_lots is a JSON array of the remaining lots (as TEXT so
-- ingestion lands it as VARCHAR).

CREATE TABLE inventory_current_stock (
    sku                  TEXT PRIMARY KEY REFERENCES inventory_units (unit_id),
    on_hand_quantity     NUMERIC(18, 4) NOT NULL,
    oldest_lot_expiry    DATE,
    on_hand_lots         TEXT NOT NULL,
    last_transaction_at  DATE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Read-only analytics role (created in 01_schema.sql) needs SELECT on all tables.
GRANT SELECT ON inventory_units, inventory_lots, inventory_transactions,
    inventory_current_stock TO dermiq_reader;
