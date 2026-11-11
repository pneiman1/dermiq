"""The store's own contract, below the intake: atomic writes, counted once.

The intake tests cover the behaviour through the front door. These go at the
store directly, because the two guarantees it owes — an add that either lands
everything or changes nothing, and one cost-bearing record per invoice key — are
what make "no partial record" and "not double-counted" true upstream.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from dermiq.invoices import (
    DuplicateInvoiceError,
    InMemoryInvoiceStore,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
    accounting_period,
)

LANDED = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)


def line(number: int = 1, total: str = "100.00") -> InvoiceLineItem:
    return InvoiceLineItem(
        line_number=number,
        description=f"line {number}",
        quantity=Decimal("1"),
        unit="each",
        unit_cost=Decimal(total),
        total_cost=Decimal(total),
        gl_account_code="5010",
    )


def record(
    *,
    fingerprint: str = "fp-1",
    supplier_id: str = "sup_a",
    invoice_number: str = "INV-1",
    period: str = "2026-09",
    status: InvoiceStatus = InvoiceStatus.EXTRACTED,
    total: str = "100.00",
    lines: tuple[InvoiceLineItem, ...] | None = None,
) -> InvoiceRecord:
    return InvoiceRecord(
        fingerprint=fingerprint,
        supplier_id=supplier_id,
        period=period,
        invoice_number=invoice_number,
        status=status,
        line_items=lines if lines is not None else (line(total=total),),
        invoice_date="2026-09-28",
        currency="USD",
        total=Decimal(total),
        job_id="job-1",
        landed_at=LANDED,
        document_filename=f"{fingerprint}.pdf",
    )


@pytest.fixture
def store() -> InMemoryInvoiceStore:
    return InMemoryInvoiceStore()


def test_an_added_record_is_findable_by_fingerprint_and_by_invoice_key(store):
    added = store.add(record())

    assert store.get("fp-1") is added
    assert store.find_invoice("sup_a", "INV-1") is added
    assert store.records() == (added,)
    assert len(store) == 1


def test_the_same_fingerprint_cannot_land_twice(store):
    store.add(record())
    with pytest.raises(DuplicateInvoiceError, match="already landed"):
        store.add(record())

    assert len(store) == 1


def test_a_second_cost_bearing_record_for_one_invoice_key_is_rejected(store):
    store.add(record())
    with pytest.raises(DuplicateInvoiceError, match="must not be counted twice"):
        store.add(record(fingerprint="fp-2"))

    # The rejected add changed nothing — not the order, not the key index.
    assert len(store) == 1
    assert store.records() == (store.get("fp-1"),)
    assert store.find_invoice("sup_a", "INV-1").fingerprint == "fp-1"
    assert store.cost_total() == Decimal("100.00")


def test_a_duplicate_record_may_land_alongside_the_one_that_counts(store):
    counted = store.add(record())
    dupe = store.add(record(fingerprint="fp-2", status=InvoiceStatus.DUPLICATE))

    assert len(store) == 2
    assert store.find_invoice("sup_a", "INV-1") is counted
    assert store.line_items_for_cost_model() == counted.line_items
    assert dupe.counts_as_cost is False


def test_a_pending_record_does_not_claim_the_invoice_key(store):
    store.add(record(status=InvoiceStatus.PENDING_REVIEW))

    assert store.find_invoice("sup_a", "INV-1") is None
    # ...so the corrected copy can still land as cost.
    corrected = store.add(record(fingerprint="fp-2"))
    assert store.find_invoice("sup_a", "INV-1") is corrected
    assert store.cost_total() == Decimal("100.00")


def test_only_extracted_records_reach_the_cost_model(store):
    store.add(record(fingerprint="fp-1", invoice_number="INV-1", total="10.00"))
    store.add(
        record(
            fingerprint="fp-2",
            invoice_number="INV-2",
            total="20.00",
            status=InvoiceStatus.PENDING_REVIEW,
        )
    )
    store.add(
        record(
            fingerprint="fp-3",
            invoice_number="INV-3",
            total="40.00",
            status=InvoiceStatus.DUPLICATE,
        )
    )

    assert store.cost_total() == Decimal("10.00")
    assert len(store.line_items_for_cost_model()) == 1
    assert [r.invoice_number for r in store.pending()] == ["INV-2"]
    assert len(store.records()) == 3


def test_records_filter_by_supplier_period_and_status(store):
    store.add(record(fingerprint="fp-1", supplier_id="sup_a", period="2026-09"))
    store.add(
        record(fingerprint="fp-2", supplier_id="sup_b", invoice_number="INV-2", period="2026-09")
    )
    store.add(
        record(fingerprint="fp-3", supplier_id="sup_a", invoice_number="INV-3", period="2026-10")
    )

    assert [r.fingerprint for r in store.records(supplier_id="sup_a")] == ["fp-1", "fp-3"]
    assert [r.fingerprint for r in store.records(period="2026-09")] == ["fp-1", "fp-2"]
    assert [
        r.fingerprint for r in store.records(supplier_id="sup_a", period="2026-10")
    ] == ["fp-3"]
    assert store.records(status=InvoiceStatus.PENDING_REVIEW) == ()


def test_records_come_back_in_landing_order(store):
    for i in range(1, 4):
        store.add(record(fingerprint=f"fp-{i}", invoice_number=f"INV-{i}"))

    assert [r.fingerprint for r in store.records()] == ["fp-1", "fp-2", "fp-3"]


def test_cost_total_sums_the_line_items_not_the_header_totals(store):
    """The cost model adds up lines; a header total nobody checked is not cost."""
    store.add(record(total="100.00", lines=(line(1, "60.00"), line(2, "40.00"))))

    assert store.cost_total() == Decimal("100.00")
    assert len(store.line_items_for_cost_model()) == 2


def test_an_empty_store_answers_zero_rather_than_raising(store):
    assert store.records() == ()
    assert store.pending() == ()
    assert store.line_items_for_cost_model() == ()
    assert store.cost_total() == Decimal("0")
    assert store.get("nope") is None
    assert store.find_invoice("sup_a", "INV-1") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-09-28", "2026-09"),
        ("2026-01-01T09:30:00+00:00", "2026-01"),
        (datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc), "2026-12"),
    ],
)
def test_accounting_period_is_the_month_the_cost_lands_in(value, expected):
    assert accounting_period(value) == expected
