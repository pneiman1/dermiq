"""Inventory / consumables generation for Del Mar Cosmetic Dermatology (chunk-11).

Models the full consumables lifecycle so the Inventory tab runs on real (fixture)
data, not stubs:

  * inventory_units   — consumable product master (one SKU per consumable service)
  * inventory_lots    — receiving events: bulk orders arriving over the 18-month
                        window, each with a per-lot actual cost and a shelf-life
                        expiry date
  * inventory_movements (loaded into the inventory_transactions table) — FIFO
                        draw-downs against lots: consumption tied to a sale,
                        waste (overage), and expiry write-offs for lots that
                        reach expiry with stock remaining
  * current_stock     — on-hand quantity per SKU today, derived from lots minus
                        everything drawn or expired

Real consumables cost runs above the catalog `default_cost` (per-lot price
variance + waste + expiry write-offs), so true margin lands below catalog margin.
Generation is deterministic given the input sales transactions and the seed.
"""
from __future__ import annotations

import json
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from dermiq.seed.catalog import SERVICES


CONSUMABLE_CATEGORIES = ("injectable", "energy_device", "skincare_retail")

CATEGORY_COST_FACTOR = {
    "injectable": 1.12,
    "energy_device": 1.15,
    "skincare_retail": 1.06,
}

# Neuromodulators are dosed in units; the name encodes the dose.
TOXIN_UNITS = {
    "BOTOX-20": 20, "BOTOX-40": 40, "BOTOX-60": 60,
    "DAXXIFY-40": 40, "DYSPORT-50": 50, "XEOMIN-30": 30,
}

# Shelf life (months) by unit_of_measure — drives lot expiry dates.
SHELF_LIFE_MONTHS = {
    "unit": 24,        # neuromodulators
    "syringe": 18,     # HA fillers
    "treatment": 36,   # energy-device consumables (tips/cartridges)
    "product": 18,     # retail skincare
}

# Fraction of consumption events with material waste, and the extra-quantity band.
# Tuned so injectable waste rate lands in the realistic ~4-5% range.
WASTE_RATE = 0.09
WASTE_MULTIPLIER_RANGE = (1.20, 1.90)

# Per-lot cost variance around the SKU's nominal unit cost.
LOT_COST_VARIANCE = 0.05

# Reorder ~one interval of demand plus a thin buffer, so steady-state on-hand is a
# few weeks of stock (not a compounding pile). Occasional bulk orders — GPO/
# manufacturer deals — over-supply a SKU and are the realistic source of expiry
# write-offs on slower movers (e.g. fillers).
REORDER_SAFETY = 1.05
BULK_ORDER_RATE = 0.06
BULK_ORDER_MULTIPLIER_RANGE = (2.0, 3.0)

# Some received stock is short-dated (distributors offload product with only a
# few months of shelf life left). Behind other on-hand stock in the FIFO queue,
# these are the realistic source of expiry write-offs within the operating window.
SHORT_DATED_RATE = 0.12
SHORT_DATED_DAYS_RANGE = (150, 270)

# Clearance buys: a bulk, deeply short-dated deal the practice couldn't resist.
# Bought in more quantity than can be used before it expires, so it sits on hand
# and shows up in "expiring soon" (and eventually as expiry write-off).
CLEARANCE_RATE = 0.03
CLEARANCE_MULTIPLIER_RANGE = (1.3, 1.8)
CLEARANCE_DAYS_RANGE = (25, 85)

# Recently-received stock that is short-dated and slightly over-bought lingers on
# hand near its expiry today — this is what populates "expiring soon" (future
# expiry), as distinct from clearance buys that mostly expired in the past.
# Recently-received lots whose expiry is anchored a few weeks out from *today*, so
# they are on hand now and genuinely expiring soon (never a past write-off). This
# populates "expiring soon" without inflating historical waste value.
RECENT_WINDOW_DAYS = 70
RECENT_SHORT_DATED_RATE = 0.50
RECENT_SHORT_DATED_DAYS_RANGE = (8, 55)
RECENT_OVERBUY_RANGE = (1.2, 1.6)


@dataclass(frozen=True)
class InventoryUnit:
    unit_id: str
    product_name: str
    category: str
    unit_of_measure: str
    service_code: str
    units_per_service: float
    unit_cost: float
    shelf_life_months: int
    par_level: float          # target on-hand floor; drives below-par alerts


@dataclass
class InventoryLot:
    lot_id: str
    sku: str                  # -> inventory_units.unit_id
    lot_number: str
    received_quantity: float
    received_date: date
    expiry_date: date
    unit_cost_actual: float


@dataclass
class InventoryMovement:
    inventory_transaction_id: str
    transaction_id: str | None    # sale it backs; null for expiry write-offs
    service_code: str
    unit_id: str
    lot_id: str | None            # lot drawn from; null only if unallocatable
    movement_type: str            # 'consumption' | 'waste' | 'expiry'
    quantity: float
    unit_cost: float
    transaction_value: float
    consumed_date: date


@dataclass
class CurrentStock:
    sku: str
    on_hand_quantity: float
    oldest_lot_expiry: date | None
    on_hand_lots: str             # JSON: [{lot_number, remaining, expiry_date}]
    last_transaction_at: date | None


def _unit_of_measure(service_code: str, category: str) -> str:
    if service_code in TOXIN_UNITS:
        return "unit"
    if category == "injectable":
        return "syringe"
    if category == "energy_device":
        return "treatment"
    return "product"


def _build_inventory_units() -> list[InventoryUnit]:
    units: list[InventoryUnit] = []
    for svc in SERVICES:
        if svc.category not in CONSUMABLE_CATEGORIES:
            continue
        uom = _unit_of_measure(svc.service_code, svc.category)
        units_per_service = float(TOXIN_UNITS.get(svc.service_code, 1))
        factor = CATEGORY_COST_FACTOR[svc.category]
        unit_cost = round(svc.unit_cost * factor / units_per_service, 4)
        # Par level ~ a few weeks of a single visit's consumption; scaled by dose.
        par_level = round(units_per_service * 8, 4)
        units.append(
            InventoryUnit(
                unit_id=f"inv_{svc.service_code.lower()}",
                product_name=f"{svc.service_name} consumable",
                category=svc.category,
                unit_of_measure=uom,
                service_code=svc.service_code,
                units_per_service=units_per_service,
                unit_cost=unit_cost,
                shelf_life_months=SHELF_LIFE_MONTHS[uom],
                par_level=par_level,
            )
        )
    return units


INVENTORY_UNITS: list[InventoryUnit] = _build_inventory_units()
_UNIT_BY_SERVICE: dict[str, InventoryUnit] = {u.service_code: u for u in INVENTORY_UNITS}


def _add_months(d: date, months: int) -> date:
    """Add months to a date, clamping the day to the month end."""
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # clamp day (e.g. Jan 31 + 1 month -> Feb 28)
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _reorder_interval_weeks(annual_demand: float) -> int:
    """Higher-velocity SKUs are reordered more often."""
    if annual_demand >= 1500:
        return 4
    if annual_demand >= 400:
        return 6
    if annual_demand >= 100:
        return 8
    return 12


def generate_inventory(
    txn_rows: list[tuple[str, str, date]],
    seed: int = 42,
    today: date | None = None,
) -> tuple[list[InventoryUnit], list[InventoryLot], list[InventoryMovement], list[CurrentStock]]:
    """Generate the full inventory lifecycle from the given sales transactions.

    Args:
        txn_rows: ``[(transaction_id, service_code, transaction_date), ...]``.
        seed: RNG seed for reproducible receiving/waste sampling.
        today: "now" for stock/expiry (defaults to date.today()).

    Returns:
        (units, lots, movements, current_stock)
    """
    random.seed(seed)
    if today is None:
        today = date.today()

    # Group consumable sales by SKU, oldest first.
    demand: dict[str, list[tuple[date, str]]] = defaultdict(list)
    for transaction_id, service_code, tdate in txn_rows:
        if service_code in _UNIT_BY_SERVICE:
            demand[service_code].append((tdate, transaction_id))

    all_lots: list[InventoryLot] = []
    movements: list[InventoryMovement] = []
    current_stock: list[CurrentStock] = []

    for service_code in sorted(demand.keys()):
        unit = _UNIT_BY_SERVICE[service_code]
        sales = sorted(demand[service_code], key=lambda x: x[0])
        if not sales:
            continue

        # Build the ordered list of draws: base consumption + occasional waste.
        draws: list[tuple[date, str, float, str]] = []  # (date, txn_id, qty, type)
        for tdate, transaction_id in sales:
            base = unit.units_per_service
            draws.append((tdate, transaction_id, base, "consumption"))
            if random.random() < WASTE_RATE:
                extra = round(base * random.uniform(*WASTE_MULTIPLIER_RANGE) - base, 4)
                if extra > 0:
                    draws.append((tdate, transaction_id, extra, "waste"))
        draws.sort(key=lambda x: x[0])

        first_date = sales[0][0]
        span_years = max((today - first_date).days / 365.0, 0.25)
        total_demand = sum(d[2] for d in draws)
        annual_demand = total_demand / span_years
        interval = timedelta(weeks=_reorder_interval_weeks(annual_demand))

        # Demand-driven reordering: keep ~one interval of demand on hand, reorder
        # when it runs low, and stop when sales stop — so on-hand doesn't pile up.
        last_sale = sales[-1][0]
        interval_days = max(interval.days, 1)
        daily_rate = total_demand / max((last_sale - first_date).days, interval_days)
        lot_target = max(unit.units_per_service, round(daily_rate * interval_days * REORDER_SAFETY, 4))
        reorder_point = round(daily_rate * interval_days * 0.4, 4)

        sku_lots: list[dict] = []   # {lot, remaining}, in receive order (FIFO)
        seq = 0

        def _receive(rdate, size_mult=1.0):
            nonlocal seq
            seq += 1
            cost = round(unit.unit_cost * random.uniform(1 - LOT_COST_VARIANCE, 1 + LOT_COST_VARIANCE), 4)
            qty = lot_target * size_mult
            # Occasional bulk order (GPO / manufacturer deal) over-supplies the SKU.
            if random.random() < BULK_ORDER_RATE:
                qty *= random.uniform(*BULK_ORDER_MULTIPLIER_RANGE)
            expiry_date = _add_months(rdate, unit.shelf_life_months)
            if random.random() < SHORT_DATED_RATE:
                expiry_date = rdate + timedelta(days=int(random.uniform(*SHORT_DATED_DAYS_RANGE)))
            # Clearance deal: over-buy of deeply short-dated stock — more than can
            # be used before it expires, so it lingers on hand near its expiry.
            if random.random() < CLEARANCE_RATE:
                qty *= random.uniform(*CLEARANCE_MULTIPLIER_RANGE)
                expiry_date = rdate + timedelta(days=int(random.uniform(*CLEARANCE_DAYS_RANGE)))
            # Recently-received short-dated stock: on hand now and expiring soon,
            # which is what the "expiring soon" view surfaces. Expiry is anchored a
            # few weeks out from today so it is always in the future (not a past
            # write-off).
            if (today - rdate).days <= RECENT_WINDOW_DAYS and random.random() < RECENT_SHORT_DATED_RATE:
                qty *= random.uniform(*RECENT_OVERBUY_RANGE)
                expiry_date = today + timedelta(days=int(random.uniform(*RECENT_SHORT_DATED_DAYS_RANGE)))
            qty = round(qty, 4)
            lot = InventoryLot(
                lot_id=f"lot_{uuid.uuid4().hex[:12]}",
                sku=unit.unit_id,
                lot_number=f"{service_code}-{rdate:%Y%m}-{seq:02d}",
                received_quantity=qty,
                received_date=rdate,
                expiry_date=expiry_date,
                unit_cost_actual=cost,
            )
            all_lots.append(lot)
            sku_lots.append({"lot": lot, "remaining": qty})

        def _expire_due(as_of):
            """Write off lots that reached expiry on/before as_of with stock left."""
            for entry in sku_lots:
                lot = entry["lot"]
                if lot.expiry_date <= as_of and entry["remaining"] > 1e-9:
                    value = round(entry["remaining"] * lot.unit_cost_actual, 4)
                    movements.append(InventoryMovement(
                        inventory_transaction_id=f"invtxn_{uuid.uuid4().hex[:12]}",
                        transaction_id=None, service_code=service_code, unit_id=unit.unit_id,
                        lot_id=lot.lot_id, movement_type="expiry", quantity=entry["remaining"],
                        unit_cost=lot.unit_cost_actual, transaction_value=value,
                        consumed_date=lot.expiry_date))
                    entry["remaining"] = 0.0

        def _available(as_of):
            return sum(e["remaining"] for e in sku_lots
                       if e["lot"].received_date <= as_of and e["lot"].expiry_date > as_of
                       and e["remaining"] > 1e-9)

        # Opening inventory: an over-sized initial stocking order a week before the
        # first sale. Slow movers won't burn it within shelf life -> some expires.
        _receive(first_date - timedelta(days=7), size_mult=2.5)

        for tdate, transaction_id, qty, mtype in draws:
            _expire_due(tdate)
            guard = 0
            while _available(tdate) < qty + reorder_point and guard < 50:
                _receive(tdate)
                guard += 1
            need = qty
            for entry in sku_lots:
                if need <= 1e-9:
                    break
                lot = entry["lot"]
                if lot.received_date > tdate or lot.expiry_date <= tdate or entry["remaining"] <= 1e-9:
                    continue
                take = min(need, entry["remaining"])
                entry["remaining"] = round(entry["remaining"] - take, 4)
                need = round(need - take, 4)
                value = round(take * lot.unit_cost_actual, 4)
                movements.append(InventoryMovement(
                    inventory_transaction_id=f"invtxn_{uuid.uuid4().hex[:12]}",
                    transaction_id=transaction_id, service_code=service_code, unit_id=unit.unit_id,
                    lot_id=lot.lot_id, movement_type=mtype, quantity=take,
                    unit_cost=lot.unit_cost_actual, transaction_value=value, consumed_date=tdate))
            # If demand outran supply (rare), record the shortfall at nominal cost
            # so cost-of-goods is never understated.
            if need > 1e-9:
                value = round(need * unit.unit_cost, 4)
                movements.append(InventoryMovement(
                    inventory_transaction_id=f"invtxn_{uuid.uuid4().hex[:12]}",
                    transaction_id=transaction_id, service_code=service_code, unit_id=unit.unit_id,
                    lot_id=None, movement_type=mtype, quantity=round(need, 4),
                    unit_cost=unit.unit_cost, transaction_value=value, consumed_date=tdate))

        # Final expiry sweep for lots that reach expiry after the last sale.
        _expire_due(today)

        # Current stock: lots not yet expired with quantity remaining.
        on_hand_entries = [
            e for e in sku_lots if e["lot"].expiry_date > today and e["remaining"] > 1e-9
        ]
        on_hand_qty = round(sum(e["remaining"] for e in on_hand_entries), 4)
        oldest_expiry = min((e["lot"].expiry_date for e in on_hand_entries), default=None)
        last_txn = max((d[0] for d in draws), default=None)
        on_hand_lots_json = json.dumps(
            [
                {
                    "lot_number": e["lot"].lot_number,
                    "remaining": e["remaining"],
                    "expiry_date": e["lot"].expiry_date.isoformat(),
                }
                for e in sorted(on_hand_entries, key=lambda e: e["lot"].expiry_date)
            ]
        )
        current_stock.append(
            CurrentStock(
                sku=unit.unit_id,
                on_hand_quantity=on_hand_qty,
                oldest_lot_expiry=oldest_expiry,
                on_hand_lots=on_hand_lots_json,
                last_transaction_at=last_txn,
            )
        )

    return INVENTORY_UNITS, all_lots, movements, current_stock
