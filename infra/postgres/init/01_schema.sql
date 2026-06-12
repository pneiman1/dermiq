-- Nextech-shaped source schema for Del Mar Cosmetic Dermatology
-- This simulates what a real clinic's transactional database looks like:
-- normalized tables, foreign keys, audit columns, soft deletes.
--
-- Loaded automatically by Postgres on first container start via
-- /docker-entrypoint-initdb.d (mapped from infra/postgres/init/).

CREATE SCHEMA IF NOT EXISTS nextech_source;
SET search_path TO nextech_source, public;

-- ============ Providers ============

CREATE TABLE IF NOT EXISTS providers (
    provider_id          TEXT PRIMARY KEY,
    full_name            TEXT NOT NULL,
    role                 TEXT NOT NULL,
    npi_number           TEXT,
    specialties          TEXT,
    hire_date            DATE,
    termination_date     DATE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ Services ============

CREATE TABLE IF NOT EXISTS services (
    service_code         TEXT PRIMARY KEY,
    service_name         TEXT NOT NULL,
    category             TEXT NOT NULL,
    default_price        NUMERIC(10, 2) NOT NULL,
    default_cost         NUMERIC(10, 2) NOT NULL,
    typical_duration_min INTEGER,
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============ Patients ============

CREATE TABLE IF NOT EXISTS patients (
    patient_id           TEXT PRIMARY KEY,
    first_name           TEXT NOT NULL,
    last_name            TEXT NOT NULL,
    date_of_birth        DATE,
    gender               TEXT,
    address_zip          TEXT,
    primary_phone        TEXT,
    primary_email        TEXT,
    source_channel       TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_patients_created_at ON patients (created_at);
CREATE INDEX IF NOT EXISTS idx_patients_source ON patients (source_channel);

-- ============ Appointments ============

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id            TEXT PRIMARY KEY,
    patient_id                TEXT NOT NULL REFERENCES patients (patient_id),
    provider_id               TEXT NOT NULL REFERENCES providers (provider_id),
    appointment_type          TEXT,
    scheduled_start           TIMESTAMPTZ NOT NULL,
    scheduled_end             TIMESTAMPTZ NOT NULL,
    actual_arrival            TIMESTAMPTZ,
    actual_departure          TIMESTAMPTZ,
    status                    TEXT NOT NULL,
    booking_lead_time_hours   INTEGER,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_appts_patient ON appointments (patient_id);
CREATE INDEX IF NOT EXISTS idx_appts_provider ON appointments (provider_id);
CREATE INDEX IF NOT EXISTS idx_appts_scheduled_start ON appointments (scheduled_start);
CREATE INDEX IF NOT EXISTS idx_appts_status ON appointments (status);

-- ============ Transactions ============

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id           TEXT PRIMARY KEY,
    patient_id               TEXT NOT NULL REFERENCES patients (patient_id),
    appointment_id           TEXT REFERENCES appointments (appointment_id),
    provider_id              TEXT NOT NULL REFERENCES providers (provider_id),
    service_code             TEXT NOT NULL REFERENCES services (service_code),
    service_category         TEXT,
    gross_amount             NUMERIC(10, 2) NOT NULL,
    discount_amount          NUMERIC(10, 2) NOT NULL DEFAULT 0,
    net_amount               NUMERIC(10, 2) NOT NULL,
    alle_redemption_units    INTEGER NOT NULL DEFAULT 0,
    payment_method           TEXT,
    transaction_date         DATE NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_txn_patient ON transactions (patient_id);
CREATE INDEX IF NOT EXISTS idx_txn_provider ON transactions (provider_id);
CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions (transaction_date);
CREATE INDEX IF NOT EXISTS idx_txn_appointment ON transactions (appointment_id);

-- ============ Permissions (read-only role for analytics ingestion) ============

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dermiq_reader') THEN
      CREATE ROLE dermiq_reader WITH LOGIN PASSWORD 'reader_local_only';
   END IF;
END
$$;

GRANT USAGE ON SCHEMA nextech_source TO dermiq_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA nextech_source TO dermiq_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA nextech_source GRANT SELECT ON TABLES TO dermiq_reader;
