"""Shared fixtures for the invoice intake tests. Stub service only, no socket.

Every test here runs against :class:`StubExtractionService`, which is also the
package default — so these tests exercise exactly the wiring a demo gets with
nothing switched on. Documents come from two places: the recorded envelopes
under ``fixtures/`` for the realistic cases, and ``canned_document`` for the
one-field-wrong payloads, which are clearer written as a dict than as a file.

Time is faked rather than waited on. :class:`FakeClock` is both the monotonic
clock and the sleep function, so a two-minute deadline passes instantly and the
sleeps the code asked for are assertable.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from dermiq.invoices import (
    InMemoryInvoiceStore,
    InvoiceDocument,
    InvoiceIntake,
    StubExtractionService,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures"

#: Fixed landing timestamp, so a record built in a test is stable across runs.
LANDED_AT = datetime(2026, 10, 6, 15, 30, tzinfo=timezone.utc)


class FakeClock:
    """Monotonic clock whose only way forward is a sleep the code asked for."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def landed_at() -> datetime:
    return LANDED_AT


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store() -> InMemoryInvoiceStore:
    return InMemoryInvoiceStore()


@pytest.fixture
def service() -> StubExtractionService:
    """The default service, answering on the first poll."""
    return StubExtractionService()


@pytest.fixture
def load_invoice():
    """Build a document from a recorded envelope under ``fixtures/``.

    The bytes are the file's bytes, unmodified — the fingerprint has to be the
    fingerprint of what is on disk for the duplicate tests to mean anything.
    The supplier defaults to the one named inside the envelope.
    """

    def load(
        name: str,
        *,
        supplier_id: str | None = None,
        period: str | None = None,
        filename: str | None = None,
    ) -> InvoiceDocument:
        path = FIXTURE_ROOT / f"{name}.json"
        content = path.read_bytes()
        return InvoiceDocument(
            supplier_id=supplier_id or json.loads(content)["invoice"]["supplier_id"],
            filename=filename or path.name,
            content=content,
            period=period,
            content_type="application/json",
        )

    return load


@pytest.fixture
def canned_document():
    """Build a document whose bytes are a canned envelope dict, for the edge cases."""

    def build(
        envelope: dict[str, Any],
        *,
        supplier_id: str = "sup_allergan_aesthetics",
        filename: str = "canned.json",
        period: str | None = None,
    ) -> InvoiceDocument:
        return InvoiceDocument(
            supplier_id=supplier_id,
            filename=filename,
            content=json.dumps(envelope).encode("utf-8"),
            period=period,
            content_type="application/json",
        )

    return build


@pytest.fixture
def invoice_envelope():
    """A clean envelope as a dict, for tests that want to break exactly one field."""

    def build(**overrides: Any) -> dict[str, Any]:
        invoice: dict[str, Any] = {
            "supplier_id": "sup_allergan_aesthetics",
            "invoice_number": "AA-90001",
            "invoice_date": "2026-09-30",
            "currency": "USD",
            "total": "300.00",
            "line_items": [
                {
                    "line_number": 1,
                    "description": "JUVEDERM VOLUMA XC 1.0mL syringe",
                    "quantity": "20",
                    "unit": "vial",
                    "unit_cost": "15.00",
                    "total_cost": "300.00",
                    "gl_account_code": "5010",
                }
            ],
        }
        invoice.update(overrides)
        return {"confidence": 0.99, "invoice": invoice}

    return build


@pytest.fixture
def make_intake(store: InMemoryInvoiceStore, clock: FakeClock):
    """Intake factory: the shared store and fake clock, plus the service given."""

    def build(service: StubExtractionService | None = None, **overrides: Any) -> InvoiceIntake:
        options: dict[str, Any] = {
            "timeout_seconds": 30.0,
            "poll_interval_seconds": 2.0,
            "clock": clock,
            "sleep": clock.sleep,
            "now": lambda: LANDED_AT,
        }
        options.update(overrides)
        return InvoiceIntake(service or StubExtractionService(), store, **options)

    return build


@pytest.fixture
def intake(service: StubExtractionService, make_intake) -> InvoiceIntake:
    return make_intake(service)


@pytest.fixture
def clean_document(load_invoice) -> InvoiceDocument:
    return load_invoice("clean_invoice")


@pytest.fixture
def flagged_document(load_invoice) -> InvoiceDocument:
    return load_invoice("flagged_invoice")
