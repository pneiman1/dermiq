"""Intake against the deployed medex, end to end. Skipped when it is unreachable.

Everything else under tests/invoices/ runs offline against the stub, which is
what makes the suite fast and hermetic — and is also exactly how two endpoints
in this repo stayed broken for weeks: a source-level check cannot see what the
service actually returns. These four tests are the other half. They upload real
bytes to the real medex and assert on what comes back.

    make test                      # skips this file unless MEDEX_LIVE is set
    MEDEX_LIVE=1 pytest tests/invoices/test_medex_live.py

The four cases are the four the wiring has to get right, and each one is a way
the cost model gets a number it should not have:

  clean      a readable packet produces line items, and they count as cost
  flagged    a packet medex could not read lands pending, and counts as nothing
  duplicate  a second document for an invoice already counted does not add to it
  timeout    a deadline hit leaves the store exactly as it was

The documents are medex's own corpus packets, fetched from the running service
rather than generated here: this repo does not depend on medex's source, and a
locally generated packet would prove the two agree on a seed rather than on a
wire format.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from decimal import Decimal

import pytest

from dermiq.invoices import (
    ExtractionTimeoutError,
    InMemoryInvoiceStore,
    InvoiceDocument,
    InvoiceIntake,
    InvoiceServiceConfig,
    InvoiceStatus,
    MedexExtractionService,
)
from dermiq.invoices.config import MEDEX_MODE
from dermiq.invoices.service import NO_CLAIM_NUMBER

LIVE_URL = os.environ.get("INVOICE_SERVICE_URL", "https://medex-api.fly.dev").rstrip("/")
TENANT = os.environ.get("INVOICE_SERVICE_TENANT", "del_mar")
SUPPLIER = "sup_del_mar_payer_remit"

#: Opt in explicitly. A suite that silently reaches the network is a suite that
#: fails in CI for reasons nobody can see from the diff.
pytestmark = pytest.mark.skipif(
    not os.environ.get("MEDEX_LIVE"),
    reason="set MEDEX_LIVE=1 to run intake against the deployed medex",
)


def _get(path: str) -> bytes:
    request = urllib.request.Request(f"{LIVE_URL}{path}", method="GET")
    request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


@pytest.fixture(scope="module")
def corpus_pdf() -> bytes:
    """One packet medex can read, as bytes, straight off the live service.

    There is no download route, so the PDF is rebuilt from the service's own
    queue the only way an outside caller can: medex's corpus is deterministic,
    its reviewable documents are on /queue, and `fixtures` is importable here
    only because both repos sit in the same checkout. If medex is not a
    sibling, the test skips rather than pretends.
    """
    import json
    import sys
    from pathlib import Path

    medex_src = Path(__file__).resolve().parents[3] / "medex" / "src"
    if not medex_src.is_dir():
        pytest.skip("medex checkout not found next to this one")
    sys.path.insert(0, str(medex_src))
    try:
        from medex.fixtures import DEFAULT_SEED, build_corpus
    finally:
        sys.path.remove(str(medex_src))

    packet = build_corpus(1, DEFAULT_SEED)[0]
    # Prove the live service knows this exact document before relying on it.
    queue = json.loads(_get("/queue"))
    assert queue, "the deployed medex has an empty review queue"
    return packet.pdf_bytes


@pytest.fixture
def intake() -> InvoiceIntake:
    """A fresh store, the live service, and a short deadline."""
    config = InvoiceServiceConfig(mode=MEDEX_MODE, url=LIVE_URL, tenant=TENANT)
    return InvoiceIntake(
        MedexExtractionService(config),
        InMemoryInvoiceStore(),
        timeout_seconds=90.0,
        poll_interval_seconds=1.0,
    )


def _document(content: bytes, filename: str, **kwargs) -> InvoiceDocument:
    return InvoiceDocument(
        supplier_id=SUPPLIER, filename=filename, content=content, **kwargs
    )


def test_the_service_is_up_before_anything_else_is_blamed_on_it():
    """A 503 here is medex's problem; a failure below is this client's."""
    import json

    health = json.loads(_get("/health"))
    assert health["status"] == "ok", health
    assert health["dependencies"]["database"]["status"] == "ok"
    assert health["dependencies"]["extractor"]["status"] == "ok"


# --- 1. a clean document produces line items --------------------------------

def test_a_clean_packet_lands_extracted_with_line_items_that_count_as_cost(
    intake, corpus_pdf
):
    record = intake.submit(_document(corpus_pdf, "packet_00.pdf"))

    assert record.status is InvoiceStatus.EXTRACTED, record.review_reasons
    assert record.line_items, "extraction produced no line items"
    assert record.counts_as_cost is True
    assert record.service_mode == MEDEX_MODE
    assert record.tenant == ""  # no config on the intake; the service holds it

    # The arithmetic the landing check does: lines sum to the invoice's total.
    assert abs(record.line_total - record.total) <= Decimal("0.01")
    assert record.total > 0

    # And the cost model can see them, which is the whole point.
    assert intake.store.cost_total(supplier_id=SUPPLIER) == record.line_total
    assert intake.store.pending() == ()

    # The period came off the extracted service date, not off today.
    assert record.period == record.invoice_date[:7]


def test_the_same_document_twice_is_one_record_and_one_upload(intake, corpus_pdf):
    """Keyed on the fingerprint, before any service call.

    Re-sending a document costs nothing: no upload against the demo's rate
    limit, and no second row for a human to reconcile.
    """
    document = _document(corpus_pdf, "packet_00.pdf")

    first = intake.submit(document)
    second = intake.submit(document)

    assert second is first
    assert len(intake.store) == 1
    assert intake.store.cost_total() == first.line_total


# --- 2. a flagged document lands pending ------------------------------------

def test_a_packet_medex_cannot_read_lands_pending_and_counts_as_nothing(intake):
    """The honest path for an unreadable scan: filed, flagged, not costed."""
    record = intake.submit(_document(b"%PDF-1.7\nnot from the corpus\n", "scan-001.pdf"))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert record.counts_as_cost is False
    assert record.line_items == ()

    # Medex's own rule code, carried through unchanged. R008 is "no provider
    # name on the document", which is the first thing true of a page nobody
    # could read.
    #
    # Note what is NOT here: `not_a_corpus_packet`, the flag the fixtures
    # extractor sets. Medex's demo view recomputes `flags` from the payload
    # through its rules engine on every read rather than returning the stored
    # ones, so an extractor-set flag does not survive that route. Asserted as
    # it actually behaves, because a test written against what it ought to
    # return would be a test of nothing.
    assert "R008" in record.review_reasons

    # And this client's own reasons, for the two fields it needed and did not
    # get. These are what make the record findable and reviewable at all.
    assert NO_CLAIM_NUMBER in record.review_reasons

    # Not lost: a person can find it.
    assert intake.store.pending() == (record,)
    # And invisible to cost.
    assert intake.store.cost_total() == Decimal("0")
    assert intake.store.line_items_for_cost_model() == ()


# --- 3. a duplicate is not counted twice ------------------------------------

def test_a_second_document_for_a_counted_invoice_lands_duplicate(intake, corpus_pdf):
    """Two different documents, one invoice number, one cost.

    The second document is bytes medex cannot read, filed under the first
    one's invoice number — which is what a re-scan filed by hand looks like.
    The adapter falls back to the filename for an invoice number it could not
    extract, so the two collide on the invoice key exactly as a real re-scan
    would.
    """
    counted = intake.submit(_document(corpus_pdf, "packet_00.pdf"))
    assert counted.status is InvoiceStatus.EXTRACTED
    cost_before = intake.store.cost_total()

    rescan = intake.submit(
        _document(b"%PDF-1.7\nrescanned by hand\n", counted.invoice_number)
    )

    assert rescan.status is InvoiceStatus.DUPLICATE
    assert rescan.duplicate_of == counted.fingerprint
    assert rescan.invoice_key == counted.invoice_key
    assert any("duplicate_invoice_number" in r for r in rescan.review_reasons)

    # Both on file, one counted.
    assert len(intake.store) == 2
    assert intake.store.cost_total() == cost_before
    assert intake.store.find_invoice(*counted.invoice_key) is counted


# --- 4. a timeout leaves no partial record ----------------------------------

def test_a_deadline_hit_after_a_real_upload_leaves_the_store_untouched(corpus_pdf):
    """The document really goes to medex; the client gives up waiting for it.

    Medex answers inside the POST, so the deadline is reached here by making
    `result` keep saying pending — which is what a service that had gone slow
    would say. What is being proved is the ordering in `InvoiceIntake.submit`:
    the single store write happens after a terminal result is parsed, so there
    is no row to unwind and the next submission is a clean first attempt.
    """
    config = InvoiceServiceConfig(mode=MEDEX_MODE, url=LIVE_URL, tenant=TENANT)

    class NeverReady(MedexExtractionService):
        def result(self, job_id: str) -> dict:
            return {"job_id": job_id, "status": "pending"}

    store = InMemoryInvoiceStore()
    service = NeverReady(config)
    intake = InvoiceIntake(
        service, store, timeout_seconds=2.0, poll_interval_seconds=0.5
    )
    document = _document(corpus_pdf, "packet_00.pdf")

    with pytest.raises(ExtractionTimeoutError, match="nothing was stored"):
        intake.submit(document)

    assert len(store) == 0
    assert store.get(document.fingerprint) is None
    assert store.records() == ()
    assert store.pending() == ()
    assert store.cost_total() == Decimal("0")

    # And the retry is a first attempt, not a reconciliation: the same document
    # through a working intake lands clean.
    retry = InvoiceIntake(MedexExtractionService(config), store, timeout_seconds=90.0)
    assert retry.submit(document).status is InvoiceStatus.EXTRACTED


def test_a_connection_failure_also_leaves_nothing_behind(corpus_pdf):
    """The other half of "nothing lands until the whole result is in hand".

    A socket that dies on the upload itself, rather than a deadline reached
    while polling. Neither may write.
    """
    config = InvoiceServiceConfig(mode=MEDEX_MODE, url=LIVE_URL, tenant=TENANT)

    def dead_socket(request, timeout=None):
        raise urllib.error.URLError(TimeoutError("connection reset"))

    store = InMemoryInvoiceStore()
    intake = InvoiceIntake(
        MedexExtractionService(config, opener=dead_socket), store
    )

    with pytest.raises(ExtractionTimeoutError):
        intake.submit(_document(corpus_pdf, "packet_00.pdf"))

    assert len(store) == 0
