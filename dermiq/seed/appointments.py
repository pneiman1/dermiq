"""Generate appointments and transactions for Del Mar Cosmetic Dermatology.

Each completed appointment produces 1-3 transaction line items. The generator
intentionally bakes in story patterns so the dashboards have something interesting
to show:

  1. Dr. Marcus Halloway (prov_001) cut hours after Q1 2026 due to knee surgery.
     His visit volume drops ~60% in Apr-May, recovers gradually.
  2. Dr. Sofia Reyes (prov_003) is the rising star: YoY visit volume up ~30%.
  3. Dr. Anita Desai (prov_005) has a low cross-sell/skincare-attach rate.
  4. Cassandra Chen, PA-C (prov_006) has high rebook rate and cross-sell.
  5. Botox waste spikes in months where a vial is dropped (random ~5% of months).
  6. Seasonality: revenue dips in January, spikes April-May ("wedding season")
     and November ("event prep").
  7. Meta Ads-acquired patients have lower LTV than other channels (worse fit).
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta

import numpy as np

from dermiq.seed.catalog import (
    PROVIDERS,
    SERVICES,
    NO_SHOW_RATE_BASELINE,
    CANCEL_RATE_BASELINE,
    OPEN_DAYS_PER_WEEK,
    AVG_VISITS_PER_PATIENT_PER_YEAR,
)
from dermiq.seed.patients import Patient


@dataclass
class Appointment:
    appointment_id: str
    patient_id: str
    provider_id: str
    appointment_type: str
    scheduled_start: datetime
    scheduled_end: datetime
    actual_arrival: datetime | None
    actual_departure: datetime | None
    status: str  # 'completed' | 'no_show' | 'cancelled'
    booking_lead_time_hours: int


@dataclass
class Transaction:
    transaction_id: str
    patient_id: str
    appointment_id: str
    provider_id: str
    service_code: str
    service_category: str
    gross_amount: float
    discount_amount: float
    net_amount: float
    alle_redemption_units: int
    payment_method: str
    transaction_date: date


# ============ Story-pattern helpers ============

def _seasonality_multiplier(d: date) -> float:
    """Practice seasonality. 1.0 = average."""
    m = d.month
    if m == 1:           return 0.78   # January slump
    if m == 2:           return 0.92
    if m in (4, 5):      return 1.20   # Wedding season
    if m == 11:          return 1.18   # Event prep / holiday refresh
    if m == 12:          return 1.10
    if m in (6, 7, 8):   return 1.05   # Summer steady
    return 1.0


def _halloway_multiplier(d: date) -> float:
    """Dr. Halloway took medical leave April-May 2026; recovered slowly."""
    if d >= date(2026, 4, 1) and d <= date(2026, 5, 31):
        return 0.40   # heavy leave
    if d >= date(2026, 6, 1) and d <= date(2026, 7, 31):
        return 0.70   # gradual recovery
    return 1.0


def _reyes_multiplier(d: date) -> float:
    """Dr. Reyes ramped up in 2026 — up ~30% YoY."""
    if d >= date(2026, 1, 1):
        return 1.30
    return 1.0


def _provider_for_visit(visit_date: date, ltv_tier: str) -> str:
    """Pick a provider weighted by their productivity baseline and story multipliers."""
    weights = []
    for prov in PROVIDERS:
        w = prov.productivity_baseline
        if prov.provider_id == "prov_001":
            w *= _halloway_multiplier(visit_date)
        elif prov.provider_id == "prov_003":
            w *= _reyes_multiplier(visit_date)
        # VIP patients prefer the senior MDs
        if ltv_tier == "vip" and prov.role == "MD":
            w *= 1.5
        weights.append(w)
    return random.choices([p.provider_id for p in PROVIDERS], weights=weights, k=1)[0]


def _service_mix_for_visit(provider_id: str, ltv_tier: str, visit_date: date) -> list:
    """Pick 1-3 services for the visit, biased by provider style and patient tier."""
    # Number of services per visit
    n_services = random.choices([1, 2, 3], weights=[0.50, 0.35, 0.15], k=1)[0]
    if ltv_tier == "vip":
        n_services = random.choices([1, 2, 3, 4], weights=[0.20, 0.35, 0.30, 0.15], k=1)[0]

    # Provider biases: who tends to do what
    provider_biases = {
        "prov_001": {"surgical": 3.0, "injectable": 2.0, "energy_device": 0.8},  # Halloway
        "prov_002": {"injectable": 2.5, "skincare_retail": 1.5},                 # Park
        "prov_003": {"energy_device": 2.5, "injectable": 1.2},                   # Reyes
        "prov_004": {"surgical": 2.0, "energy_device": 1.5},                     # Whitfield
        "prov_005": {"injectable": 2.0, "skincare_retail": 0.4},                 # Desai — low attach
        "prov_006": {"injectable": 2.0, "skincare_retail": 1.8},                 # Chen — high attach
        "prov_007": {"skincare_retail": 4.0},                                    # Voss
    }
    bias = provider_biases.get(provider_id, {})

    chosen = []
    for _ in range(n_services):
        weights = []
        for svc in SERVICES:
            w = svc.weight
            w *= bias.get(svc.category, 1.0)
            # VIP tier biased toward higher-ticket services
            if ltv_tier == "vip" and svc.gross_price > 800:
                w *= 1.8
            if ltv_tier == "low" and svc.gross_price > 800:
                w *= 0.3
            weights.append(w)
        chosen.append(random.choices(SERVICES, weights=weights, k=1)[0])
    return chosen


def _visits_for_patient(patient: Patient, end_date: date) -> int:
    """Decide how many visits this patient had between signup and now."""
    days_since_signup = (end_date - patient.created_at).days
    years = days_since_signup / 365.0
    tier_mult = {"vip": 3.5, "high": 2.0, "standard": 1.0, "low": 0.5}[patient.ltv_tier]
    # Meta Ads patients are a poor fit — lower visit frequency
    channel_mult = 0.6 if patient.source_channel == "instagram_meta" else 1.0
    base = AVG_VISITS_PER_PATIENT_PER_YEAR * years * tier_mult * channel_mult
    return max(1, int(np.random.poisson(max(0.5, base))))


def _random_visit_time(visit_date: date) -> datetime:
    """Schedule a visit on visit_date during business hours (9am-7pm)."""
    hour = random.randint(9, 18)
    minute = random.choice([0, 15, 30, 45])
    return datetime.combine(visit_date, datetime.min.time()).replace(hour=hour, minute=minute)


# ============ Main generator ============

def generate_appointments_and_transactions(
    patients: list[Patient],
    seed: int = 42,
) -> tuple[list[Appointment], list[Transaction]]:
    """Generate appointments + transactions for all patients.

    Returns:
        (appointments, transactions)
    """
    random.seed(seed)
    np.random.seed(seed)

    today = date.today()
    appointments: list[Appointment] = []
    transactions: list[Transaction] = []

    for patient in patients:
        n_visits = _visits_for_patient(patient, today)
        days_window = (today - patient.created_at).days
        if days_window <= 0:
            continue

        # Spread visits roughly evenly with some jitter, weighted toward later dates
        visit_dates: list[date] = []
        for _ in range(n_visits):
            offset = int(np.random.beta(1.5, 1.5) * days_window)
            d = patient.created_at + timedelta(days=offset)
            # Skip Sundays (closed)
            if d.weekday() == 6:
                d = d - timedelta(days=1)
            # Apply seasonality bias by re-sampling if unlucky
            seas = _seasonality_multiplier(d)
            if random.random() > seas / 1.5:
                continue
            visit_dates.append(d)

        for v_date in visit_dates:
            provider_id = _provider_for_visit(v_date, patient.ltv_tier)

            # Status
            r = random.random()
            if r < NO_SHOW_RATE_BASELINE:
                status = "no_show"
            elif r < NO_SHOW_RATE_BASELINE + CANCEL_RATE_BASELINE:
                status = "cancelled"
            else:
                status = "completed"

            scheduled_start = _random_visit_time(v_date)
            scheduled_end = scheduled_start + timedelta(minutes=30)

            actual_arrival = None
            actual_departure = None
            if status == "completed":
                arrival_delta = random.randint(-5, 20)
                actual_arrival = scheduled_start + timedelta(minutes=arrival_delta)
                actual_departure = actual_arrival + timedelta(minutes=random.choice([15, 30, 45, 60]))

            appt_id = f"appt_{uuid.uuid4().hex[:12]}"
            booking_lead = int(np.clip(np.random.exponential(scale=300), 1, 2000))
            appointments.append(Appointment(
                appointment_id=appt_id,
                patient_id=patient.patient_id,
                provider_id=provider_id,
                appointment_type="standard",
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                actual_arrival=actual_arrival,
                actual_departure=actual_departure,
                status=status,
                booking_lead_time_hours=booking_lead,
            ))

            # Only completed visits generate transactions
            if status != "completed":
                continue

            services = _service_mix_for_visit(provider_id, patient.ltv_tier, v_date)
            for svc in services:
                discount_pct = random.choices([0, 0, 0, 0, 0.05, 0.10], k=1)[0]
                gross = svc.gross_price
                discount = round(gross * discount_pct, 2)
                net = round(gross - discount, 2)
                # Alle redemption: ~12% of injectable transactions
                alle_units = 0
                if svc.category == "injectable" and random.random() < 0.12:
                    alle_units = random.choice([100, 150, 200])

                transactions.append(Transaction(
                    transaction_id=f"txn_{uuid.uuid4().hex[:12]}",
                    patient_id=patient.patient_id,
                    appointment_id=appt_id,
                    provider_id=provider_id,
                    service_code=svc.service_code,
                    service_category=svc.category,
                    gross_amount=gross,
                    discount_amount=discount,
                    net_amount=net,
                    alle_redemption_units=alle_units,
                    payment_method=random.choices(
                        ["card", "card", "card", "cash", "carecredit"], k=1
                    )[0],
                    transaction_date=v_date,
                ))

    return appointments, transactions


def appointments_to_dicts(appts: list[Appointment]) -> list[dict]:
    out = []
    for a in appts:
        d = asdict(a)
        # CSV-friendly: datetimes to ISO strings, None preserved
        for k in ("scheduled_start", "scheduled_end", "actual_arrival", "actual_departure"):
            if d[k] is not None:
                d[k] = d[k].isoformat()
        out.append(d)
    return out


def transactions_to_dicts(txns: list[Transaction]) -> list[dict]:
    out = []
    for t in txns:
        d = asdict(t)
        d["transaction_date"] = d["transaction_date"].isoformat()
        out.append(d)
    return out