"""Generate patient records for Del Mar Cosmetic Dermatology.

Each patient gets:
- patient_id (deterministic from seed)
- demographic info (name, age, gender, zip)
- acquisition channel and signup date
- a "lifetime value tier" that biases their future visit behavior

Patient visit history is generated separately (in appointments.py) — this file
only produces the patient master records.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, asdict
from datetime import date, timedelta

import numpy as np
from faker import Faker

from dermiq.seed.catalog import (
    ACQUISITION_CHANNELS,
    SD_ZIPS,
    TOTAL_PATIENTS,
    MONTHS_OF_HISTORY,
)


@dataclass
class Patient:
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: str
    zip_code: str
    source_channel: str
    created_at: date
    ltv_tier: str  # 'vip' | 'high' | 'standard' | 'low' — biases future spend


def _weighted_choice(items: list[tuple], weights_index: int = 1):
    """Pick one item by its weight. items must be list of tuples where items[i][weights_index] is the weight."""
    weights = [item[weights_index] for item in items]
    return random.choices(items, weights=weights, k=1)[0]


def _age_distribution() -> int:
    """Cosmetic derm skews 30-60, with a long tail to 75."""
    # Truncated normal: mean 45, stddev 12, clipped to [22, 80]
    age = int(np.clip(np.random.normal(45, 12), 22, 80))
    return age


def _ltv_tier() -> str:
    """Distribution of patient value tiers — heavily skewed toward 'standard'."""
    return random.choices(
        ["vip", "high", "standard", "low"],
        weights=[0.05, 0.18, 0.55, 0.22],
        k=1,
    )[0]


def generate_patients(
    n_patients: int = TOTAL_PATIENTS,
    months_of_history: int = MONTHS_OF_HISTORY,
    seed: int = 42,
) -> list[Patient]:
    """Generate n_patients patient records distributed across the history window.

    Args:
        n_patients: total number of patients to generate
        months_of_history: how far back signup dates can go
        seed: random seed for reproducibility

    Returns:
        List of Patient dataclasses
    """
    random.seed(seed)
    np.random.seed(seed)
    fake = Faker()
    Faker.seed(seed)

    today = date.today()
    earliest = today - timedelta(days=months_of_history * 30)

    patients: list[Patient] = []
    for i in range(n_patients):
        # Gender: cosmetic derm is heavily female-skewed
        gender = random.choices(["F", "M"], weights=[0.85, 0.15], k=1)[0]
        first_name = fake.first_name_female() if gender == "F" else fake.first_name_male()
        last_name = fake.last_name()

        # Age and DOB
        age = _age_distribution()
        dob = today - timedelta(days=age * 365 + random.randint(0, 364))

        # Zip
        zip_code = _weighted_choice(SD_ZIPS, weights_index=1)[0]

        # Acquisition channel
        channel = _weighted_choice(ACQUISITION_CHANNELS, weights_index=1)[0]

        # Signup date — uniform over history window
        days_in_window = (today - earliest).days
        created_at = earliest + timedelta(days=random.randint(0, days_in_window))

        patients.append(Patient(
            patient_id=f"pat_{i:06d}",
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            gender=gender,
            zip_code=zip_code,
            source_channel=channel,
            created_at=created_at,
            ltv_tier=_ltv_tier(),
        ))

    return patients


def patients_to_dicts(patients: list[Patient]) -> list[dict]:
    """Convert Patient dataclasses to dicts for CSV writing."""
    return [asdict(p) for p in patients]