"""Invoice intake, against the stub service. Four behaviours carry the weight.

* A clean invoice produces line items, against the supplier and the period.
* A flagged extraction lands pending and cannot reach the cost model.
* A duplicate invoice is not counted twice — neither the same document resent
  nor a second copy of an invoice number that already counts.
* A service timeout leaves no record at all, partial or otherwise.

The rest of the file is the edges around those: the landing checks, the poll
loop, and the parse guards that have to fire before anything is written.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from dermiq.invoices import (
    ExtractionFailedError,
    ExtractionServiceError,
    ExtractionTimeoutError,
    InvoiceDocument,
    InvoiceIntake,
    InvoiceIntegrityError,
    InvoiceStatus,
    StubExtractionService,
)
from dermiq.invoices.intake import (
    DUPLICATE_INVOICE,
    NO_INVOICE_DATE,
    NO_LINE_ITEMS,
    TOTAL_MISMATCH,
)
from dermiq.invoices.service import UNREADABLE_REASON


# --- a clean invoice produces line items -------------------------------------

def test_a_clean_invoice_produces_line_items(intake, clean_document):
    record = intake.submit(clean_document)

    assert record.status is InvoiceStatus.EXTRACTED
    assert record.review_reasons == ()
    assert record.counts_as_cost is True
    assert [line.line_number for line in record.line_items] == [1, 2]

    hops, freight = record.line_items
    assert hops.description == "BOTOX Cosmetic 100U vial, 2026 harvest"
    assert hops.quantity == Decimal("250")
    assert hops.unit == "vial"
    assert hops.unit_cost == Decimal("17.25")
    assert hops.total_cost == Decimal("4312.50")
    assert hops.gl_account_code == "5010"
    assert freight.total_cost == Decimal("500.00")
    # Money stays exact: Decimal in, Decimal out, and the lines add up to the
    # invoice's own total to the cent.
    assert record.line_total == record.total == Decimal("4812.50")


def test_line_items_land_against_the_supplier_and_the_period(
    intake, store, clean_document, landed_at
):
    record = intake.submit(clean_document)

    # The period is the invoice date's accounting month, not the landing month.
    assert record.period == "2026-09"
    assert record.supplier_id == "sup_allergan_aesthetics"
    assert record.invoice_number == "AA-88120"
    assert record.invoice_date == "2026-09-28"
    assert record.currency == "USD"
    assert record.landed_at == landed_at
    assert record.document_filename == "clean_invoice.json"
    assert record.job_id == "stub-job-1"
    assert record.service_mode == "stub"
    assert record.confidence == pytest.approx(0.98)

    assert store.records(supplier_id="sup_allergan_aesthetics", period="2026-09") == (record,)
    assert (
        store.line_items_for_cost_model(supplier_id="sup_allergan_aesthetics", period="2026-09")
        == record.line_items
    )
    assert store.cost_total(supplier_id="sup_allergan_aesthetics", period="2026-09") == Decimal("4812.50")
    # A different period holds none of it.
    assert store.cost_total(supplier_id="sup_allergan_aesthetics", period="2026-08") == Decimal("0")


def test_a_declared_period_overrides_the_invoice_date(intake, store, load_invoice):
    """A late invoice books to the month the brewery posted it in."""
    record = intake.submit(load_invoice("clean_invoice", period="2026-10"))

    assert record.period == "2026-10"
    assert record.invoice_date == "2026-09-28"
    assert store.cost_total(period="2026-10") == Decimal("4812.50")
    assert store.cost_total(period="2026-09") == Decimal("0")


def test_two_suppliers_keep_their_own_cost(intake, store, clean_document, load_invoice):
    intake.submit(clean_document)
    intake.submit(load_invoice("second_supplier_invoice"))

    assert store.cost_total(supplier_id="sup_allergan_aesthetics") == Decimal("4812.50")
    assert store.cost_total(supplier_id="sup_gw_malting") == Decimal("1260.00")
    assert store.cost_total() == Decimal("6072.50")


# --- a flagged extraction lands pending --------------------------------------

def test_a_flagged_invoice_lands_pending_and_keeps_the_service_reasons(
    intake, store, flagged_document
):
    record = intake.submit(flagged_document)

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert record.counts_as_cost is False
    assert record.review_reasons == ("low_confidence_on_total", "handwritten_amendment")
    # Pending does not mean discarded: the line items are on file for whoever
    # reviews it.
    assert len(record.line_items) == 1
    assert record.total == Decimal("2100.00")
    assert store.pending(supplier_id="sup_gw_malting") == (record,)


def test_a_flagged_invoice_never_enters_the_cost_model(intake, store, flagged_document):
    intake.submit(flagged_document)

    assert store.line_items_for_cost_model() == ()
    assert store.cost_total() == Decimal("0")
    assert store.cost_total(supplier_id="sup_gw_malting", period="2026-09") == Decimal("0")
    # And it did not quietly claim the invoice key either — a corrected re-scan
    # of the same invoice can still land as cost later.
    assert store.find_invoice("sup_gw_malting", "GW-5521") is None


def test_a_corrected_rescan_of_a_pending_invoice_can_still_land_as_cost(
    intake, store, flagged_document, canned_document, invoice_envelope
):
    """The whole point of not letting a pending record claim the invoice key."""
    flagged = intake.submit(flagged_document)
    assert flagged.status is InvoiceStatus.PENDING_REVIEW

    corrected = intake.submit(
        canned_document(
            invoice_envelope(
                supplier_id="sup_gw_malting",
                invoice_number="GW-5521",
                invoice_date="2026-09-15",
                total="2100.00",
                line_items=[
                    {
                        "line_number": 1,
                        "description": "2-row pale malt, 44 vial sacks",
                        "quantity": "60",
                        "unit": "sack",
                        "unit_cost": "35.00",
                        "total_cost": "2100.00",
                        "gl_account_code": "5020",
                    }
                ],
            ),
            supplier_id="sup_gw_malting",
            filename="flagged_invoice_rescan.json",
        )
    )

    assert corrected.status is InvoiceStatus.EXTRACTED
    assert store.cost_total(supplier_id="sup_gw_malting") == Decimal("2100.00")
    # Both copies are on file; only one is cost.
    assert len(store.records(supplier_id="sup_gw_malting")) == 2


def test_lines_that_do_not_sum_to_the_total_land_pending(intake, store, load_invoice):
    """A confident extraction whose arithmetic fails is still not cost."""
    record = intake.submit(load_invoice("total_mismatch_invoice"))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert len(record.review_reasons) == 1
    assert record.review_reasons[0].startswith(TOTAL_MISMATCH)
    assert "lines 1000.00 vs total 1500.00" in record.review_reasons[0]
    assert store.cost_total() == Decimal("0")


def test_a_penny_of_rounding_is_not_a_review(
    intake, store, canned_document, invoice_envelope
):
    """One cent of tolerance, so penny rounding on a tax line is not held."""
    record = intake.submit(canned_document(invoice_envelope(total="300.01")))

    assert record.status is InvoiceStatus.EXTRACTED
    # The lines are the cost; the header total is kept as the service read it.
    assert store.cost_total() == Decimal("300.00")
    assert record.total == Decimal("300.01")


def test_two_cents_of_drift_is_a_review(intake, store, canned_document, invoice_envelope):
    record = intake.submit(canned_document(invoice_envelope(total="300.02")))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert record.review_reasons[0].startswith(TOTAL_MISMATCH)
    assert store.cost_total() == Decimal("0")


def test_an_undated_invoice_lands_pending_in_the_month_it_arrived(
    intake, store, load_invoice
):
    record = intake.submit(load_invoice("undated_invoice"))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert NO_INVOICE_DATE in record.review_reasons
    # Filed under the landing month so a human can find it, and out of cost.
    assert record.period == "2026-10"
    assert store.cost_total(period="2026-10") == Decimal("0")
    assert store.pending(period="2026-10") == (record,)


def test_an_undated_invoice_with_a_declared_period_is_not_flagged_for_the_date(
    intake, store, load_invoice
):
    record = intake.submit(load_invoice("undated_invoice", period="2026-09"))

    assert record.status is InvoiceStatus.EXTRACTED
    assert record.period == "2026-09"
    assert store.cost_total(period="2026-09") == Decimal("880.00")


def test_an_extraction_with_no_line_items_lands_pending(
    intake, store, canned_document, invoice_envelope
):
    record = intake.submit(canned_document(invoice_envelope(total="0", line_items=[])))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert NO_LINE_ITEMS in record.review_reasons
    assert store.cost_total() == Decimal("0")


def test_a_document_the_stub_cannot_read_lands_pending_rather_than_costing_nothing(
    intake, store
):
    """A real PDF through the stub: flagged, zero lines, zero cost, on file."""
    record = intake.submit(
        InvoiceDocument(
            supplier_id="sup_allergan_aesthetics",
            filename="scan_0042.pdf",
            content=b"%PDF-1.7\n%\xd0\xd4\xc5\xd8 not a canned envelope",
        )
    )

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert UNREADABLE_REASON in record.review_reasons
    assert record.line_items == ()
    assert store.cost_total() == Decimal("0")
    assert store.pending() == (record,)


def test_a_flagged_result_with_no_stated_reason_still_says_it_was_flagged(
    intake, canned_document, invoice_envelope
):
    envelope = invoice_envelope()
    envelope["status"] = "needs_review"
    record = intake.submit(canned_document(envelope))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert record.review_reasons == ("flagged_by_extraction_service",)


def test_a_service_review_flag_without_the_needs_review_status_is_still_pending(
    intake, canned_document, invoice_envelope
):
    """Either signal is enough; neither is allowed to be lost in the other."""
    envelope = invoice_envelope()
    envelope["status"] = "succeeded"
    envelope["review"] = {"flagged": True, "reasons": ["price_differs_from_contract"]}
    record = intake.submit(canned_document(envelope))

    assert record.status is InvoiceStatus.PENDING_REVIEW
    assert record.review_reasons == ("price_differs_from_contract",)


# --- a duplicate invoice is not double-counted -------------------------------

def test_the_same_document_twice_is_counted_once_and_sent_once(
    intake, store, service, clean_document
):
    first = intake.submit(clean_document)
    second = intake.submit(clean_document)

    assert second is first
    assert len(store) == 1
    assert store.cost_total() == Decimal("4812.50")
    # Not re-sent: the fingerprint check happens before the POST, so a resent
    # document costs no extraction call.
    assert len(service.submissions) == 1


def test_a_rescan_of_an_invoice_that_already_counts_lands_as_a_duplicate(
    intake, store, clean_document, load_invoice
):
    """Different bytes, same invoice number. On file, and out of the cost model."""
    counted = intake.submit(clean_document)
    rescan = intake.submit(load_invoice("rescanned_invoice"))

    assert rescan.fingerprint != counted.fingerprint
    assert rescan.status is InvoiceStatus.DUPLICATE
    assert rescan.counts_as_cost is False
    assert rescan.duplicate_of == counted.fingerprint
    assert any(reason.startswith(DUPLICATE_INVOICE) for reason in rescan.review_reasons)

    # Both arrivals are auditable; the cost is still one invoice.
    assert len(store) == 2
    assert store.cost_total() == Decimal("4812.50")
    assert store.line_items_for_cost_model() == counted.line_items
    assert store.find_invoice("sup_allergan_aesthetics", "AA-88120") is counted
    # A duplicate is not pending either — there is nothing for a human to fix.
    assert store.pending() == ()


def test_a_third_copy_does_not_count_either(
    intake, store, clean_document, load_invoice, canned_document, invoice_envelope
):
    """A third distinct document for one invoice number, counted zero more times."""
    intake.submit(clean_document)
    intake.submit(load_invoice("rescanned_invoice"))
    third = intake.submit(
        canned_document(
            invoice_envelope(invoice_number="AA-88120", invoice_date="2026-09-28"),
            filename="third_copy.json",
        )
    )

    assert third.status is InvoiceStatus.DUPLICATE
    assert len(store) == 3
    assert store.cost_total() == Decimal("4812.50")
    assert len(store.line_items_for_cost_model()) == 2


def test_the_same_bytes_from_two_suppliers_are_two_different_documents(clean_document):
    """Fingerprints are supplier-scoped: shared boilerplate is not a duplicate."""
    other = InvoiceDocument(
        supplier_id="sup_gw_malting",
        filename=clean_document.filename,
        content=clean_document.content,
        content_type="application/json",
    )
    assert other.fingerprint != clean_document.fingerprint
    # Same supplier, same bytes, different filename: still one document.
    same = InvoiceDocument(
        supplier_id=clean_document.supplier_id,
        filename="rescanned_under_another_name.json",
        content=clean_document.content,
        content_type="application/json",
    )
    assert same.fingerprint == clean_document.fingerprint


# --- a timeout leaves no partial record --------------------------------------

def test_a_service_timeout_leaves_no_record_at_all(store, make_intake, clean_document):
    intake = make_intake(StubExtractionService(polls_until_ready=10_000), timeout_seconds=10.0)

    with pytest.raises(ExtractionTimeoutError, match="nothing was stored"):
        intake.submit(clean_document)

    # No record, no partial record, nothing claimed.
    assert len(store) == 0
    assert store.records() == ()
    assert store.get(clean_document.fingerprint) is None
    assert store.find_invoice("sup_allergan_aesthetics", "AA-88120") is None
    assert store.line_items_for_cost_model() == ()
    assert store.pending() == ()
    assert store.cost_total() == Decimal("0")


def test_a_timed_out_document_can_be_resubmitted_cleanly(store, make_intake, clean_document):
    """Because nothing landed, the retry is a first attempt, not a reconciliation."""
    service = StubExtractionService(polls_until_ready=10_000)
    intake = make_intake(service, timeout_seconds=10.0)
    with pytest.raises(ExtractionTimeoutError):
        intake.submit(clean_document)

    service.polls_until_ready = 0  # the service recovers
    record = intake.submit(clean_document)

    assert record.status is InvoiceStatus.EXTRACTED
    assert len(store) == 1
    assert store.cost_total() == Decimal("4812.50")


def test_the_poll_loop_honours_the_deadline_and_never_sleeps_past_it(
    make_intake, clock, clean_document
):
    intake = make_intake(
        StubExtractionService(polls_until_ready=10_000),
        timeout_seconds=5.0,
        poll_interval_seconds=2.0,
    )
    with pytest.raises(ExtractionTimeoutError):
        intake.submit(clean_document)

    # 2 + 2 + 1: the last wait is clipped to the deadline rather than overrunning it.
    assert clock.sleeps == [2.0, 2.0, 1.0]
    assert clock.now == 5.0


def test_a_slow_extraction_that_finishes_inside_the_deadline_lands(
    make_intake, clock, clean_document
):
    service = StubExtractionService(polls_until_ready=3)
    record = make_intake(service).submit(clean_document)

    assert record.status is InvoiceStatus.EXTRACTED
    assert len(service.polls) == 4  # three pending answers, then the result
    assert clock.sleeps == [2.0, 2.0, 2.0]


def test_a_job_that_is_already_done_costs_one_poll_and_no_sleep(
    intake, service, clock, clean_document
):
    intake.submit(clean_document)

    assert len(service.polls) == 1
    assert clock.sleeps == []


def test_a_service_error_mid_poll_leaves_no_record(store, make_intake, clean_document):
    class BrokenService(StubExtractionService):
        def result(self, job_id: str):
            raise ExtractionServiceError("connection reset")

    with pytest.raises(ExtractionServiceError, match="connection reset"):
        make_intake(BrokenService()).submit(clean_document)

    assert len(store) == 0


def test_a_failed_extraction_raises_and_leaves_no_record(
    store, make_intake, canned_document, invoice_envelope
):
    envelope = invoice_envelope()
    envelope["status"] = "failed"
    envelope["error"] = "document unreadable"

    with pytest.raises(ExtractionFailedError, match="document unreadable"):
        make_intake().submit(canned_document(envelope))

    assert len(store) == 0


def test_an_unknown_job_status_is_not_polled_forever(
    store, make_intake, clock, clean_document
):
    class ChattyService(StubExtractionService):
        def result(self, job_id: str):
            return {"job_id": job_id, "status": "transcribing"}

    with pytest.raises(InvoiceIntegrityError, match="unknown job status 'transcribing'"):
        make_intake(ChattyService()).submit(clean_document)

    assert len(store) == 0
    assert clock.sleeps == []


# --- parse guards: every one of these must fire before anything is written ----

@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"job_id": "j", "status": "succeeded"}, "carries no invoice object"),
        (
            {"job_id": "j", "status": "succeeded", "invoice": {"invoice_number": "", "total": "1"}},
            "no invoice number",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "invoice": {"invoice_number": "X-1", "line_items": []},
            },
            "total is missing",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "invoice": {"invoice_number": "X-1", "total": "1", "line_items": {}},
            },
            "line_items is not a list",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "invoice": {
                    "invoice_number": "X-1",
                    "total": "1",
                    "line_items": [{"description": "x"}],
                },
            },
            "line_number=None is not an integer",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "invoice": {
                    "invoice_number": "X-1",
                    "total": "1",
                    "line_items": [{"line_number": 1, "description": ""}],
                },
            },
            "description is empty",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "invoice": {
                    "invoice_number": "X-1",
                    "total": "1",
                    "line_items": [{"line_number": 1, "description": "x", "quantity": "two"}],
                },
            },
            "quantity='two' is not a number",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "invoice": {
                    "invoice_number": "X-1",
                    "total": "1",
                    "line_items": [
                        {
                            "line_number": 1,
                            "description": "x",
                            "quantity": "1",
                            "unit_cost": "1",
                        }
                    ],
                },
            },
            "total_cost is missing",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "confidence": "very",
                "invoice": {"invoice_number": "X-1", "total": "1", "line_items": []},
            },
            "confidence='very' is not a number",
        ),
        (
            {
                "job_id": "j",
                "status": "succeeded",
                "review": [],
                "invoice": {"invoice_number": "X-1", "total": "1", "line_items": []},
            },
            "review is not an object",
        ),
        (["not", "an", "object"], "is not an object"),
    ],
)
def test_an_unusable_response_raises_and_writes_nothing(store, make_intake, payload, expected):
    class CannedService(StubExtractionService):
        def result(self, job_id: str):
            return payload

    document = InvoiceDocument(
        supplier_id="sup_allergan_aesthetics", filename="x.pdf", content=b"%PDF-1.7 x"
    )

    with pytest.raises(InvoiceIntegrityError, match=expected):
        make_intake(CannedService()).submit(document)
    assert len(store) == 0


def test_a_mismatched_supplier_is_a_misfiling_not_a_review(store, make_intake, load_invoice):
    """Charging one supplier's cost to another is never a thing to flag and keep."""
    document = load_invoice("clean_invoice", supplier_id="sup_gw_malting")

    with pytest.raises(InvoiceIntegrityError, match="does not match the document's supplier"):
        make_intake().submit(document)
    assert len(store) == 0


def test_an_invoice_date_that_is_not_a_date_is_refused(
    store, make_intake, canned_document, invoice_envelope
):
    with pytest.raises(InvoiceIntegrityError, match="is not an ISO date"):
        make_intake().submit(canned_document(invoice_envelope(invoice_date="last Tuesday")))
    assert len(store) == 0


# --- documents the intake refuses to take at all -----------------------------

def test_a_document_with_no_supplier_is_refused():
    with pytest.raises(InvoiceIntegrityError, match="names no supplier"):
        InvoiceDocument(supplier_id="", filename="x.pdf", content=b"x")


def test_an_empty_document_is_refused():
    with pytest.raises(InvoiceIntegrityError, match="is empty"):
        InvoiceDocument(supplier_id="sup_x", filename="x.pdf", content=b"")


@pytest.mark.parametrize("period", ["2026-13", "2026-00", "202609", "2026-9", "September"])
def test_a_declared_period_must_be_a_month(period):
    with pytest.raises(InvoiceIntegrityError, match="expected YYYY-MM"):
        InvoiceDocument(supplier_id="sup_x", filename="x.pdf", content=b"x", period=period)


@pytest.mark.parametrize("bad", [0, -1])
def test_a_nonpositive_deadline_or_interval_is_refused(bad):
    with pytest.raises(ValueError, match="timeout_seconds"):
        InvoiceIntake(StubExtractionService(), timeout_seconds=bad)
    with pytest.raises(ValueError, match="poll_interval_seconds"):
        InvoiceIntake(StubExtractionService(), poll_interval_seconds=bad)
