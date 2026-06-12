"""Catalog: static reference data for Del Mar Cosmetic Dermatology.

This file is intentionally hand-curated, not generated. It reflects what an
actual upper-tier La Jolla cosmetic dermatology practice would look like —
modeled after publicly visible practices like Cosmetic Laser Dermatology,
but with fully fabricated names and details.
"""
from __future__ import annotations

from dataclasses import dataclass


PRACTICE_NAME = "Del Mar Cosmetic Dermatology"
PRACTICE_CITY = "Del Mar"
PRACTICE_STATE = "CA"
PRACTICE_TIMEZONE = "America/Los_Angeles"


@dataclass(frozen=True)
class Provider:
    provider_id: str
    full_name: str
    role: str           # "MD", "DO", "PA", "RN", "Aesthetician"
    specialties: str
    hire_year: int
    productivity_baseline: float  # multiplier applied to baseline visits/day; 1.0 = average


PROVIDERS: list[Provider] = [
    Provider("prov_001", "Marcus Halloway, MD", "MD",
             "Surgical dermatology, injectables, vein", 2008, 1.40),
    Provider("prov_002", "Vivian Park, MD",     "MD",
             "Cosmetic dermatology, injectables",       2014, 1.55),
    Provider("prov_003", "Sofia Reyes, MD",     "MD",
             "Dermatology, lasers, devices",            2018, 1.30),
    Provider("prov_004", "James Whitfield, DO", "DO",
             "Body sculpting, surgical, vein",          2016, 1.10),
    Provider("prov_005", "Anita Desai, MD",     "MD",
             "Injectables, laser",                      2020, 0.90),
    Provider("prov_006", "Cassandra Chen, PA-C","PA",
             "Injectables, body",                       2019, 1.20),
    Provider("prov_007", "Elena Voss",          "Aesthetician",
             "Hydrafacial, peels, skincare",            2017, 0.80),
]


@dataclass(frozen=True)
class Service:
    service_code: str
    service_name: str
    category: str           # injectable | energy_device | skincare_retail | membership | surgical | consult
    gross_price: float
    unit_cost: float
    typical_duration_min: int
    weight: float           # relative probability of being chosen for a visit


SERVICES: list[Service] = [
    # --- Injectables: neuromodulators ---
    Service("BOTOX-20",      "Botox 20 units",      "injectable", 240.0,  80.0,  15, 25),
    Service("BOTOX-40",      "Botox 40 units",      "injectable", 480.0, 160.0,  20, 18),
    Service("BOTOX-60",      "Botox 60 units",      "injectable", 720.0, 240.0,  25, 10),
    Service("DAXXIFY-40",    "Daxxify 40 units",    "injectable", 560.0, 200.0,  20,  6),
    Service("DYSPORT-50",    "Dysport 50 units",    "injectable", 350.0, 130.0,  20,  5),
    Service("XEOMIN-30",     "Xeomin 30 units",     "injectable", 330.0, 120.0,  15,  3),

    # --- Injectables: HA fillers ---
    Service("VOLUMA-1",      "Voluma 1 syringe",    "injectable", 850.0, 280.0,  30,  9),
    Service("JUVEDERM-1",    "Juvederm Ultra Plus", "injectable", 750.0, 250.0,  30, 10),
    Service("VOLLURE-1",     "Vollure 1 syringe",   "injectable", 780.0, 260.0,  30,  4),
    Service("VOLBELLA-1",    "Volbella 1 syringe",  "injectable", 720.0, 240.0,  30,  3),
    Service("RESTYLANE-1",   "Restylane 1 syringe", "injectable", 720.0, 230.0,  30,  5),
    Service("RHA-3",         "RHA 3 syringe",       "injectable", 820.0, 280.0,  30,  4),
    Service("SCULPTRA-1",    "Sculptra 1 vial",     "injectable", 950.0, 310.0,  40,  2),

    # --- Energy devices ---
    Service("MOXI-FACE",     "Moxi face treatment",        "energy_device",  600.0,  80.0, 45,  7),
    Service("FRAXEL-FACE",   "Fraxel Dual face",           "energy_device", 1100.0, 140.0, 60,  4),
    Service("VBEAM-FACE",    "Vbeam Prima face",           "energy_device",  650.0,  90.0, 30,  5),
    Service("PICOWAY-FACE",  "Picoway face",               "energy_device",  900.0, 120.0, 45,  3),
    Service("BBL-FACE",      "BBL Hero face",              "energy_device",  500.0,  60.0, 30,  6),
    Service("MORPHEUS8",     "Morpheus8 face",             "energy_device", 1500.0, 200.0, 60,  3),
    Service("THERMAGE-FLX",  "Thermage FLX face",          "energy_device", 3000.0, 400.0, 75,  1),
    Service("ULTHERAPY",     "Ultherapy lower face/neck",  "energy_device", 3500.0, 450.0, 90,  1),
    Service("COOL-ABDOMEN",  "CoolSculpting Elite abdomen","energy_device", 1500.0, 200.0, 60,  3),
    Service("RF-MICRO",      "RF Microneedling face",      "energy_device", 1200.0, 150.0, 60,  4),

    # --- Aesthetician services ---
    Service("HYDRAFACIAL",   "Hydrafacial Deluxe",   "skincare_retail", 250.0, 35.0, 50,  8),
    Service("JETPEEL",       "JetPeel facial",       "skincare_retail", 200.0, 25.0, 40,  3),
    Service("VI-PEEL",       "VI Peel",              "skincare_retail", 350.0, 50.0, 45,  3),
    Service("DERMAPLANE",    "Dermaplaning",         "skincare_retail", 120.0, 15.0, 30,  4),

    # --- Skincare retail (products) ---
    Service("SKINCEUTICALS", "SkinCeuticals product","skincare_retail", 180.0, 60.0,  5,  9),
    Service("ZO-SKIN",       "ZO Skin Health product","skincare_retail",165.0, 55.0,  5,  6),
    Service("OBAGI",         "Obagi product",        "skincare_retail", 175.0, 58.0,  5,  4),

    # --- Memberships ---
    Service("MEMBERSHIP-VIP","Inner Circle membership","membership",  2400.0,   0.0,  10,  2),

    # --- Signature treatments ---
    Service("TAKE10",        "Take10 (BTX+filler combo)","injectable", 1450.0, 480.0, 45,  5),
    Service("TAKE5",         "Take5",                    "injectable",  790.0, 260.0, 30,  4),
    Service("3XFACIAL",      "3xFacial",                 "skincare_retail", 850.0, 110.0, 90, 2),

    # --- Surgical / vein ---
    Service("SURG-VEIN",     "Sclerotherapy session",    "surgical",     650.0,  80.0, 45,  3),
    Service("SURG-MOLE",     "Mole removal",             "surgical",     400.0,  50.0, 30,  2),

    # --- Consults ---
    Service("CONSULT-NEW",   "New patient consult",      "consult",       75.0,   0.0, 30,  6),
    Service("CONSULT-FOLLOW","Follow-up consult",        "consult",       50.0,   0.0, 15,  5),
]


# Acquisition channels with relative weights and approximate annual ad spend in USD
ACQUISITION_CHANNELS: list[tuple[str, float, float]] = [
    # (channel_name, weight_of_acquisition, annual_spend_usd)
    ("google_ads",       0.26,  84_000.0),
    ("instagram_meta",   0.20,  72_000.0),
    ("referral",         0.22,       0.0),   # Inner Circle referrals
    ("realself",         0.08,  18_000.0),
    ("alle_directory",   0.07,       0.0),   # Allergan-driven, no direct spend
    ("walkin",           0.05,       0.0),
    ("other",            0.12,       0.0),
]


# San Diego coastal ZIP codes weighted by realistic patient distribution
SD_ZIPS: list[tuple[str, float]] = [
    ("92014", 0.18),  # Del Mar
    ("92037", 0.20),  # La Jolla
    ("92130", 0.15),  # Carmel Valley
    ("92127", 0.10),  # 4S Ranch / Rancho Santa Fe
    ("92067", 0.08),  # Rancho Santa Fe
    ("92024", 0.10),  # Encinitas
    ("92075", 0.06),  # Solana Beach
    ("92129", 0.05),  # Rancho Penasquitos
    ("92122", 0.04),  # University City
    ("92121", 0.04),  # Sorrento Valley
]


# Practice operating parameters
TOTAL_PATIENTS = 3_500
MONTHS_OF_HISTORY = 18
OPEN_DAYS_PER_WEEK = 6           # Mon-Sat
OPEN_HOURS_PER_DAY = 10          # 9am-7pm
AVG_VISITS_PER_PATIENT_PER_YEAR = 2.4
NO_SHOW_RATE_BASELINE = 0.05
CANCEL_RATE_BASELINE = 0.03