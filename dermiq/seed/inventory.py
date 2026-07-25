"""Inventory / consumables generation for Del Mar Cosmetic Dermatology (chunk-11).

Every injectable, energy-device and retail service burns a consumable. This
module derives a consumable product master from the service catalog and then,
given the sales transactions that actually happened, generates the consumption
events behind them.

The point of the feature is *true* margin: real consumables cost runs a bit
above the catalog `default_cost` (real acquisition prices + waste), so true
margin lands below the catalog margin. Two effects drive that gap:

  1. A per-category cost factor (real acquisition > catalog assumption).
  2. Waste on ~7% of transactions (overfill, a dropped Botox vial) — echoing
     the waste story baked into the appointment generator.

Generation is deterministic given the input transactions and the seed, so
re-running the loader reproduces identical inventory rows.
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import date

from dermiq.seed.catalog import SERVICES


# Service categories that consume tracked inventory. Consults, memberships and
# surgical time have no product COGS worth modeling here.
CONSUMABLE_CATEGORIES = ("injectable", "energy_device", "skincare_retail")

# Real acquisition cost as a multiple of the catalog default_cost. Real-world
# unit prices sit above the round numbers baked into the service catalog.
CATEGORY_COST_FACTOR = {
    "injectable": 1.12,
    "energy_device": 1.15,
    "skincare_retail": 1.06,
}

# Neuromodulators are dosed in units; the service name encodes the dose. Mapping
# these to real per-unit quantities exercises quantity * unit_cost arithmetic
# (and is where the NUMBER(20,4)/NUMBER(38,4) precision spread comes from).
TOXIN_UNITS = {
    "BOTOX-20": 20,
    "BOTOX-40": 40,
    "BOTOX-60": 60,
    "DAXXIFY-40": 40,
    "DYSPORT-50": 50,
    "XEOMIN-30": 30,
}

# Fraction of consumption events with material waste, and the extra-quantity band.
WASTE_RATE = 0.07
WASTE_MULTIPLIER_RANGE = (1.10, 1.50)


@dataclass(frozen=True)
class InventoryUnit:
    unit_id: str
    product_name: str
    category: str
    unit_of_measure: str
    service_code: str
    units_per_service: float
    unit_cost: float


@dataclass
class InventoryTransaction:
    inventory_transaction_id: str
    transaction_id: str
    service_code: str
    unit_id: str
    quantity: float
    unit_cost: float
    transaction_value: float
    consumed_date: date


def _unit_of_measure(service_code: str, category: str) -> str:
    if service_code in TOXIN_UNITS:
        return "unit"
    if category == "injectable":
        return "syringe"
    if category == "energy_device":
        return "treatment"
    return "product"


def _build_inventory_units() -> list[InventoryUnit]:
    """One consumable per consumable-category service, priced off the catalog.

    unit_cost is set so that base consumption (units_per_service * unit_cost)
    equals default_cost * category_factor — i.e. a controlled markup over the
    catalog cost — then waste is layered on per transaction at consumption time.
    """
    units: list[InventoryUnit] = []
    for svc in SERVICES:
        if svc.category not in CONSUMABLE_CATEGORIES:
            continue
        uom = _unit_of_measure(svc.service_code, svc.category)
        units_per_service = float(TOXIN_UNITS.get(svc.service_code, 1))
        factor = CATEGORY_COST_FACTOR[svc.category]
        # Guard the divide; units_per_service is always >= 1 here.
        unit_cost = round(svc.unit_cost * factor / units_per_service, 4)
        units.append(
            InventoryUnit(
                unit_id=f"inv_{svc.service_code.lower()}",
                product_name=f"{svc.service_name} consumable",
                category=svc.category,
                unit_of_measure=uom,
                service_code=svc.service_code,
                units_per_service=units_per_service,
                unit_cost=unit_cost,
            )
        )
    return units


INVENTORY_UNITS: list[InventoryUnit] = _build_inventory_units()

# service_code -> InventoryUnit, for fast lookup during consumption generation.
_UNIT_BY_SERVICE: dict[str, InventoryUnit] = {u.service_code: u for u in INVENTORY_UNITS}


def generate_inventory_transactions(
    txn_rows: list[tuple[str, str, date]],
    seed: int = 42,
) -> list[InventoryTransaction]:
    """Generate consumption events for the given sales transactions.

    Args:
        txn_rows: ``[(transaction_id, service_code, transaction_date), ...]`` for
            the sales transactions already in the source database.
        seed: RNG seed for reproducible waste sampling.

    Returns:
        One InventoryTransaction per sales transaction whose service consumes
        tracked inventory. Sales of consults/memberships/etc. produce nothing.
    """
    random.seed(seed)
    out: list[InventoryTransaction] = []

    for transaction_id, service_code, consumed_date in txn_rows:
        unit = _UNIT_BY_SERVICE.get(service_code)
        if unit is None:
            continue  # service has no tracked consumable

        quantity = unit.units_per_service
        # Waste: overfill or a dropped vial inflates the quantity consumed.
        if random.random() < WASTE_RATE:
            quantity *= random.uniform(*WASTE_MULTIPLIER_RANGE)

        quantity = round(quantity, 4)
        transaction_value = round(quantity * unit.unit_cost, 4)

        out.append(
            InventoryTransaction(
                inventory_transaction_id=f"invtxn_{uuid.uuid4().hex[:12]}",
                transaction_id=transaction_id,
                service_code=service_code,
                unit_id=unit.unit_id,
                quantity=quantity,
                unit_cost=unit.unit_cost,
                transaction_value=transaction_value,
                consumed_date=consumed_date,
            )
        )

    return out
