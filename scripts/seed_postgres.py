"""Load generated Del Mar data directly into the Postgres source database.

This is a one-time backfill: it represents the data state at the moment a
clinic onboards. After this runs, the analytics pipeline reads from Postgres
on every scheduled run. The data generators (catalog, patients, appointments)
are NOT part of the runtime pipeline -- they are a fixture tool.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from platform_core.utils.logging import configure_logging, get_logger

from dermiq.seed.appointments import generate_appointments_and_transactions
from dermiq.seed.catalog import PROVIDERS, SERVICES
from dermiq.seed.patients import generate_patients

log = get_logger(__name__)


POSTGRES_URL = os.environ.get(
    "POSTGRES_SOURCE_URL",
    "postgresql://dermiq:dermiq_local_only@localhost:5432/del_mar_source",
)


def _truncate_all(cur) -> None:
    """Wipe existing rows. Order matters due to FKs (children first)."""
    log.info("truncate_source_tables")
    cur.execute("""
        TRUNCATE TABLE
            nextech_source.transactions,
            nextech_source.appointments,
            nextech_source.patients,
            nextech_source.services,
            nextech_source.providers
        RESTART IDENTITY CASCADE
    """)


def _load_providers(cur) -> int:
    rows = [
        (
            p.provider_id,
            p.full_name,
            p.role,
            None,  # npi_number — could mock if we wanted
            p.specialties,
            None,  # hire_date — not generated; would be from catalog if useful
            None,  # termination_date
        )
        for p in PROVIDERS
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.providers
           (provider_id, full_name, role, npi_number, specialties, hire_date, termination_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=200,
    )
    return len(rows)


def _load_services(cur) -> int:
    rows = [
        (
            s.service_code,
            s.service_name,
            s.category,
            s.gross_price,
            s.unit_cost,
            s.typical_duration_min,
            True,
        )
        for s in SERVICES
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.services
           (service_code, service_name, category, default_price, default_cost,
            typical_duration_min, active)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=200,
    )
    return len(rows)


def _load_patients(cur, patients) -> int:
    rows = [
        (
            p.patient_id,
            p.first_name,
            p.last_name,
            p.date_of_birth,
            p.gender,
            p.zip_code,
            None,  # primary_phone
            None,  # primary_email
            p.source_channel,
            datetime.combine(p.created_at, datetime.min.time(), tzinfo=timezone.utc),
        )
        for p in patients
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.patients
           (patient_id, first_name, last_name, date_of_birth, gender,
            address_zip, primary_phone, primary_email, source_channel, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=1000,
    )
    return len(rows)


def _load_appointments(cur, appts) -> int:
    rows = [
        (
            a.appointment_id,
            a.patient_id,
            a.provider_id,
            a.appointment_type,
            a.scheduled_start,
            a.scheduled_end,
            a.actual_arrival,
            a.actual_departure,
            a.status,
            a.booking_lead_time_hours,
        )
        for a in appts
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.appointments
           (appointment_id, patient_id, provider_id, appointment_type,
            scheduled_start, scheduled_end, actual_arrival, actual_departure,
            status, booking_lead_time_hours)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=1000,
    )
    return len(rows)


def _load_transactions(cur, txns) -> int:
    rows = [
        (
            t.transaction_id,
            t.patient_id,
            t.appointment_id,
            t.provider_id,
            t.service_code,
            t.service_category,
            t.gross_amount,
            t.discount_amount,
            t.net_amount,
            t.alle_redemption_units,
            t.payment_method,
            t.transaction_date,
        )
        for t in txns
    ]
    psycopg2.extras.execute_batch(
        cur,
        """INSERT INTO nextech_source.transactions
           (transaction_id, patient_id, appointment_id, provider_id, service_code,
            service_category, gross_amount, discount_amount, net_amount,
            alle_redemption_units, payment_method, transaction_date)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        rows,
        page_size=1000,
    )
    return len(rows)


def main() -> None:
    configure_logging()
    log.info("seed_postgres_start", url=POSTGRES_URL.split("@")[-1])

    log.info("generating_patients")
    patients = generate_patients()
    log.info("generating_appointments_and_transactions")
    appts, txns = generate_appointments_and_transactions(patients)

    with psycopg2.connect(POSTGRES_URL) as conn:
        with conn.cursor() as cur:
            _truncate_all(cur)
            n_prov = _load_providers(cur)
            n_svc = _load_services(cur)
            n_pat = _load_patients(cur, patients)
            n_appt = _load_appointments(cur, appts)
            n_txn = _load_transactions(cur, txns)
        conn.commit()

    log.info(
        "seed_postgres_complete",
        providers=n_prov,
        services=n_svc,
        patients=n_pat,
        appointments=n_appt,
        transactions=n_txn,
    )
    print("\n=== Postgres source database loaded ===")
    print(f"  providers      : {n_prov:,}")
    print(f"  services       : {n_svc:,}")
    print(f"  patients       : {n_pat:,}")
    print(f"  appointments   : {n_appt:,}")
    print(f"  transactions   : {n_txn:,}")
    print()


if __name__ == "__main__":
    main()
