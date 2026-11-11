"""The two service implementations, as far as they can be tested offline.

The stub gets the real coverage — it is what the suite and a demo run against.
For the medex path there is no service to talk to here, so what is tested is
everything up to the socket: the URLs, the tenant header, the error mapping,
and above all the translation, which is where this adapter earns its keep. An
autouse fixture makes a socket raise, so a test that reached the network would
fail rather than hang.

`tests/invoices/test_medex_live.py` is the other half: the same translation
against the real deployed service, skipped unless it is reachable.
"""
from __future__ import annotations

import json
import socket
import urllib.error
from decimal import Decimal

import pytest

from dermiq.invoices import (
    ExtractionServiceError,
    ExtractionTimeoutError,
    InvoiceDocument,
    InvoiceServiceConfig,
    JobStatus,
    MedexExtractionService,
    StubExtractionService,
)
from dermiq.invoices.service import (
    ASSUMED_CURRENCY,
    NO_CLAIM_NUMBER,
    NO_SERVICE_DATE,
    RESULT_PATH,
    SERVICE_UNIT,
    SUBMIT_PATH,
    TENANT_HEADER,
    UNREADABLE_REASON,
)

CONFIG = InvoiceServiceConfig(
    mode="medex", url="https://medex-api.fly.dev", tenant="del_mar"
)


@pytest.fixture(autouse=True)
def no_sockets(monkeypatch):
    """Nothing in this module may open a socket; prove it rather than assume it."""

    def refuse(*args, **kwargs):
        raise AssertionError("this test tried to open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


class FakeResponse:
    """Enough of an http.client.HTTPResponse for urlopen's context manager."""

    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode("utf-8") if not isinstance(
            payload, bytes
        ) else payload

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class RecordingOpener:
    """Captures the requests the service would have made."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[object] = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeout = timeout
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return FakeResponse(response)


def document(content: bytes = b"%PDF-1.7 packet", **kwargs) -> InvoiceDocument:
    options = {
        "supplier_id": "sup_allergan_aesthetics",
        "filename": "packet_00.pdf",
        "content": content,
    }
    options.update(kwargs)
    return InvoiceDocument(**options)


def medex_view(**overrides) -> dict:
    """One medex document view, in the shape the live service returns.

    Copied from a real response rather than invented — see
    test_invoice_service's sibling live test, which asserts the two agree.
    """
    view = {
        "doc_hash": "aFLxeGe1a7e_L1IGjxRwCQ",
        "schema_version": "0.1.0",
        "state": "extracted",
        "revision": 0,
        "flags": [],
        "auto_ok": True,
        "min_confidence": 1.0,
        "created_at": "2026-11-11T21:44:04.894516+00:00",
        "source_name": "demo upload",
        "pages": [],
        "fields": {
            "provider_name": {"name": "provider_name", "value": "Del Mar Dermatology", "confidence": 1.0},
            "patient_name": {"name": "patient_name", "value": "OVINGTON, H.", "confidence": 1.0},
            "claim_number": {"name": "claim_number", "value": "CLM-2024-66635", "confidence": 1.0},
            "date_range_start": {"name": "date_range_start", "value": "2026-06-27", "confidence": 1.0},
            "date_range_end": {"name": "date_range_end", "value": "2026-08-27", "confidence": 1.0},
        },
        "line_items": [
            {
                "date_of_service": "2026-06-27",
                "cpt": "20610",
                "description": "ARTHROCENTESIS MAJOR JOINT",
                "units": "3",
                "billed": "357.90",
                "adjustment": "0.00",
                "paid": "357.90",
            },
            {
                "date_of_service": "2026-06-28",
                "cpt": "11042",
                "description": "DEBRIDEMENT SUBQ TISSUE",
                "units": "1",
                "billed": "142.10",
                "adjustment": "-20.00",
                "paid": "122.10",
            },
        ],
        "total_billed": "500.00",
        "total_paid": "480.00",
    }
    view.update(overrides)
    return view


# --- the stub: the default, and what the rest of the suite runs on -----------

def test_the_stub_replays_the_canned_envelope_carried_by_the_document():
    canned = {
        "invoice": {
            "supplier_id": "sup_allergan_aesthetics",
            "invoice_number": "AA-1",
            "invoice_date": "2026-09-01",
            "total": "10.00",
            "line_items": [],
        }
    }
    service = StubExtractionService()
    doc = document(json.dumps(canned).encode("utf-8"), content_type="application/json")

    job_id = service.submit(doc)
    payload = service.result(job_id)

    assert job_id == "stub-job-1"
    assert payload["status"] == JobStatus.SUCCEEDED.value
    assert payload["invoice"]["invoice_number"] == "AA-1"
    # The fingerprint is echoed back the way a real service echoes a document id.
    assert payload["document_fingerprint"] == doc.fingerprint
    assert service.submissions == [doc]
    assert service.polls == [job_id]


def test_the_stub_flags_a_document_it_cannot_read():
    service = StubExtractionService()
    payload = service.result(service.submit(document()))

    assert payload["status"] == JobStatus.NEEDS_REVIEW.value
    assert payload["review"] == {"flagged": True, "reasons": [UNREADABLE_REASON]}
    # No line items invented for a document nobody could read.
    assert payload["invoice"]["line_items"] == []


def test_the_stub_defaults_the_supplier_to_the_documents_own():
    service = StubExtractionService()
    canned = {"invoice": {"invoice_number": "AA-2", "total": "1", "line_items": []}}
    doc = document(json.dumps(canned).encode("utf-8"), content_type="application/json")

    payload = service.result(service.submit(doc))

    assert payload["invoice"]["supplier_id"] == "sup_allergan_aesthetics"


def test_the_stub_can_be_made_to_take_several_polls():
    service = StubExtractionService(polls_until_ready=2)
    job_id = service.submit(document())

    assert service.result(job_id)["status"] == JobStatus.PENDING.value
    assert service.result(job_id)["status"] == JobStatus.PENDING.value
    assert service.result(job_id)["status"] == JobStatus.NEEDS_REVIEW.value
    assert service.polls == [job_id] * 3


def test_the_stubs_poll_counter_is_per_job():
    service = StubExtractionService(polls_until_ready=1)
    first = service.submit(document(b"%PDF one"))
    second = service.submit(document(b"%PDF two"))

    assert service.result(first)["status"] == JobStatus.PENDING.value
    assert service.result(second)["status"] == JobStatus.PENDING.value
    assert service.result(first)["status"] != JobStatus.PENDING.value
    assert second == "stub-job-2"


def test_the_stub_hands_out_copies_so_a_caller_cannot_rewrite_the_result():
    service = StubExtractionService()
    job_id = service.submit(document())

    service.result(job_id)["invoice"]["line_items"].append({"line_number": 99})

    assert service.result(job_id)["invoice"]["line_items"] == []


def test_the_stub_refuses_a_job_it_never_issued():
    with pytest.raises(ExtractionServiceError, match="no job 'nope'"):
        StubExtractionService().result("nope")


def test_a_negative_poll_count_is_refused():
    with pytest.raises(ValueError, match="polls_until_ready"):
        StubExtractionService(polls_until_ready=-1)


# --- medex: the translation -------------------------------------------------
#
# This is the part that breaks if medex's view ever changes shape, so it is
# tested field by field rather than through one round-trip assertion.


def test_the_translation_maps_every_field_the_contract_needs():
    doc = document()
    envelope = MedexExtractionService.translate(medex_view(), document=doc)

    assert envelope["job_id"] == "aFLxeGe1a7e_L1IGjxRwCQ"
    assert envelope["status"] == JobStatus.SUCCEEDED.value
    assert envelope["document_fingerprint"] == doc.fingerprint
    assert envelope["confidence"] == 1.0
    assert envelope["review"] == {"flagged": False, "reasons": []}

    invoice = envelope["invoice"]
    assert invoice["invoice_number"] == "CLM-2024-66635"
    # The END of the service period: the month the cost belongs to.
    assert invoice["invoice_date"] == "2026-08-27"
    assert invoice["currency"] == ASSUMED_CURRENCY
    assert invoice["total"] == "500.00"


def test_the_supplier_is_the_documents_not_the_extracted_provider_name():
    """A name off a page is not a key in this warehouse.

    Mapping provider_name onto supplier_id would make
    ExtractionResult.from_payload's mis-filing check fire on every document,
    because the two are different kinds of thing.
    """
    doc = document(supplier_id="sup_galderma")
    envelope = MedexExtractionService.translate(medex_view(), document=doc)

    assert envelope["invoice"]["supplier_id"] == "sup_galderma"


def test_line_items_carry_the_billed_amount_as_the_line_total():
    lines = MedexExtractionService.translate(medex_view(), document=document())[
        "invoice"
    ]["line_items"]

    assert [line["line_number"] for line in lines] == [1, 2]
    first = lines[0]
    assert first["description"] == "ARTHROCENTESIS MAJOR JOINT"
    assert first["quantity"] == "3"
    assert first["unit"] == SERVICE_UNIT
    assert first["total_cost"] == "357.90"
    # Derived, because medex records units and the billed amount but no rate.
    assert first["unit_cost"] == "119.30"
    assert first["gl_account_code"] == "20610"


def test_the_derived_unit_cost_never_moves_the_line_total():
    """357.90 / 3 divides; 142.10 / 3 does not. The total must not round.

    The lines-sum-to-total check upstairs is meant to test medex's arithmetic.
    If this adapter recomputed total_cost from a rounded unit_cost it would be
    testing the adapter's rounding instead, and a perfectly good document
    would land pending.
    """
    view = medex_view()
    view["line_items"] = [
        {"cpt": "11042", "description": "DEBRIDEMENT", "units": "3", "billed": "142.10"}
    ]
    line = MedexExtractionService.translate(view, document=document())["invoice"][
        "line_items"
    ][0]

    assert line["total_cost"] == "142.10"
    assert Decimal(line["unit_cost"]) * Decimal(line["quantity"]) != Decimal("142.10")


def test_a_line_with_no_units_costs_what_one_of_it_costs():
    view = medex_view()
    view["line_items"] = [{"cpt": "99213", "description": "OFFICE VISIT", "billed": "95.00"}]
    line = MedexExtractionService.translate(view, document=document())["invoice"][
        "line_items"
    ][0]

    assert (line["quantity"], line["unit_cost"], line["total_cost"]) == (
        "1",
        "95.00",
        "95.00",
    )


def test_a_line_with_zero_units_does_not_divide_by_zero():
    view = medex_view()
    view["line_items"] = [
        {"cpt": "99213", "description": "OFFICE VISIT", "units": "0", "billed": "95.00"}
    ]
    line = MedexExtractionService.translate(view, document=document())["invoice"][
        "line_items"
    ][0]

    assert line["unit_cost"] == "95.00"


def test_a_line_with_no_description_falls_back_to_its_cpt_then_to_its_position():
    view = medex_view()
    view["line_items"] = [
        {"cpt": "99213", "description": None, "units": "1", "billed": "1.00"},
        {"cpt": None, "description": "", "units": "1", "billed": "2.00"},
    ]
    lines = MedexExtractionService.translate(view, document=document())["invoice"][
        "line_items"
    ]

    assert lines[0]["description"] == "99213"
    assert lines[1]["description"] == "unlabelled line 2"


def test_a_rule_flag_makes_the_extraction_need_review():
    envelope = MedexExtractionService.translate(
        medex_view(flags=["total_billed_does_not_match_lines"], auto_ok=False),
        document=document(),
    )

    assert envelope["status"] == JobStatus.NEEDS_REVIEW.value
    assert envelope["review"]["flagged"] is True
    # Medex's own flag string is carried through, not re-worded.
    assert "total_billed_does_not_match_lines" in envelope["review"]["reasons"]


def test_auto_ok_false_alone_is_enough_to_need_review():
    """A document medex would not auto-approve is not one this client counts."""
    envelope = MedexExtractionService.translate(
        medex_view(auto_ok=False), document=document()
    )

    assert envelope["status"] == JobStatus.NEEDS_REVIEW.value


def test_a_packet_medex_could_not_read_is_filed_under_its_filename_not_refused():
    """The unreadable path must land pending, not raise.

    `fields` present with null values is exactly what medex returns for a PDF
    that is not in its corpus. Refusing it here would turn an unreadable scan
    into a failed intake and lose the document.
    """
    view = medex_view(
        flags=["not_a_corpus_packet"],
        auto_ok=False,
        min_confidence=0.0,
        line_items=[],
        total_billed=None,
        total_paid=None,
        fields={
            name: {"name": name, "value": None, "confidence": 0.0}
            for name in (
                "provider_name",
                "patient_name",
                "claim_number",
                "date_range_start",
                "date_range_end",
            )
        },
    )
    envelope = MedexExtractionService.translate(
        view, document=document(filename="somebody-elses.pdf")
    )

    assert envelope["status"] == JobStatus.NEEDS_REVIEW.value
    assert envelope["invoice"]["invoice_number"] == "somebody-elses.pdf"
    assert envelope["invoice"]["total"] == "0"
    assert envelope["invoice"]["line_items"] == []
    for reason in (NO_CLAIM_NUMBER, NO_SERVICE_DATE, "not_a_corpus_packet"):
        assert reason in envelope["review"]["reasons"]


def test_a_missing_end_date_falls_back_to_the_start_of_the_service_period():
    view = medex_view()
    view["fields"] = dict(view["fields"])
    view["fields"]["date_range_end"] = {"name": "date_range_end", "value": None}
    envelope = MedexExtractionService.translate(view, document=document())

    assert envelope["invoice"]["invoice_date"] == "2026-06-27"
    assert NO_SERVICE_DATE not in envelope["review"]["reasons"]


def test_a_view_that_is_not_an_object_is_refused():
    with pytest.raises(ExtractionServiceError, match="expected a JSON object"):
        MedexExtractionService.translate(["not", "a", "view"], document=document())


def test_fields_that_are_not_an_object_are_refused():
    with pytest.raises(ExtractionServiceError, match="fields is not an object"):
        MedexExtractionService.translate(medex_view(fields=[]), document=document())


def test_line_items_that_are_not_a_list_are_refused():
    with pytest.raises(ExtractionServiceError, match="line_items is not a list"):
        MedexExtractionService.translate(
            medex_view(line_items="357.90"), document=document()
        )


def test_a_line_item_that_is_not_an_object_is_refused():
    with pytest.raises(ExtractionServiceError, match="line 1: not an object"):
        MedexExtractionService.translate(
            medex_view(line_items=["357.90"]), document=document()
        )


# --- medex: the transport, up to the socket ---------------------------------

def test_submit_posts_the_document_bytes_with_the_tenant_header():
    opener = RecordingOpener(medex_view())
    service = MedexExtractionService(CONFIG, opener=opener)

    job_id = service.submit(document(period="2026-08"))

    assert job_id == "aFLxeGe1a7e_L1IGjxRwCQ"
    request = opener.requests[0]
    assert request.full_url == f"{CONFIG.url}{SUBMIT_PATH}"
    assert request.method == "POST"
    assert request.get_header(TENANT_HEADER.lower().capitalize()) == "del_mar"
    # The raw PDF, not multipart: medex's demo route reads the body as the file.
    assert request.get_header("Content-type") == "application/pdf"
    assert request.data == b"%PDF-1.7 packet"


def test_the_result_is_the_envelope_the_post_already_returned():
    """Medex extracts inside the POST, so there is nothing to poll for.

    One request for one document. A second HTTP call would be a second upload
    against the demo's per-caller rate limit, for an answer already in hand.
    """
    opener = RecordingOpener(medex_view())
    service = MedexExtractionService(CONFIG, opener=opener)

    job_id = service.submit(document())
    payload = service.result(job_id)

    assert len(opener.requests) == 1
    assert payload["status"] == JobStatus.SUCCEEDED.value


def test_the_held_envelope_is_handed_out_as_a_copy():
    service = MedexExtractionService(CONFIG, opener=RecordingOpener(medex_view()))
    job_id = service.submit(document())

    service.result(job_id)["invoice"]["line_items"].clear()

    assert service.result(job_id)["invoice"]["line_items"] != []


def test_a_token_this_service_never_issued_is_refused():
    """`result` is only callable for a token `submit` returned.

    Not a limitation worth hiding: translating a view needs the document it was
    for — the fingerprint and the supplier both come from the document, not
    from medex — so a token with no document on record cannot be translated.
    """
    service = MedexExtractionService(CONFIG, opener=RecordingOpener())

    with pytest.raises(ExtractionServiceError, match="no document on record"):
        service.result("some-token")


def test_a_submit_with_no_token_is_an_error_not_a_silent_success():
    service = MedexExtractionService(
        CONFIG, opener=RecordingOpener({"accepted": True, "fields": {}})
    )

    with pytest.raises(ExtractionServiceError, match="returned no doc_hash"):
        service.submit(document())


def test_the_result_path_is_used_when_a_known_token_has_no_held_envelope():
    service = MedexExtractionService(CONFIG, opener=RecordingOpener(medex_view()))
    job_id = service.submit(document())

    # Drop the held answer, keeping the document: the re-fetch path.
    service._envelopes.clear()
    service._opener = RecordingOpener(medex_view())
    service.result(job_id)

    request = service._opener.requests[0]
    assert request.full_url == f"{CONFIG.url}{RESULT_PATH.format(job_id=job_id)}"
    assert request.method == "GET"


def test_a_config_without_a_url_or_tenant_is_refused_at_construction():
    from dermiq.invoices import InvoiceConfigError

    with pytest.raises(InvoiceConfigError, match="needs both a URL and a tenant"):
        MedexExtractionService(InvoiceServiceConfig(mode="medex", url="", tenant="x"))


def test_a_socket_timeout_becomes_an_extraction_timeout():
    service = MedexExtractionService(
        CONFIG, opener=RecordingOpener(TimeoutError("timed out"))
    )

    with pytest.raises(ExtractionTimeoutError, match="timed out"):
        service.submit(document())


def test_a_urlerror_wrapping_a_timeout_becomes_an_extraction_timeout():
    service = MedexExtractionService(
        CONFIG, opener=RecordingOpener(urllib.error.URLError(TimeoutError("slow")))
    )

    with pytest.raises(ExtractionTimeoutError):
        service.submit(document())


def test_an_http_error_carries_the_status_and_the_body():
    error = urllib.error.HTTPError(
        url=f"{CONFIG.url}{SUBMIT_PATH}",
        code=413,
        msg="Payload Too Large",
        hdrs=None,
        fp=None,
    )
    error.read = lambda: b"document exceeds 10MiB"  # type: ignore[method-assign]
    service = MedexExtractionService(CONFIG, opener=RecordingOpener(error))

    with pytest.raises(ExtractionServiceError, match="HTTP 413: document exceeds 10MiB"):
        service.submit(document())


def test_the_demos_rate_limit_is_reported_as_itself():
    """429 is the one HTTP error an operator will actually see.

    It is not a bug in this client and the message has to say so, or the first
    person to hit it goes looking in the wrong repo.
    """
    error = urllib.error.HTTPError(
        url=f"{CONFIG.url}{SUBMIT_PATH}", code=429, msg="Too Many Requests",
        hdrs=None, fp=None,
    )
    error.read = lambda: b"rate limit"  # type: ignore[method-assign]
    service = MedexExtractionService(CONFIG, opener=RecordingOpener(error))

    with pytest.raises(ExtractionServiceError, match="HTTP 429"):
        service.submit(document())


def test_a_connection_failure_is_reported_as_itself():
    service = MedexExtractionService(
        CONFIG, opener=RecordingOpener(urllib.error.URLError("name resolution failed"))
    )

    with pytest.raises(ExtractionServiceError, match="name resolution failed"):
        service.submit(document())


@pytest.mark.parametrize(
    ("body", "expected"),
    [(b"<html>502</html>", "non-JSON"), (b'["not", "an", "object"]', "expected a JSON object")],
)
def test_a_response_that_is_not_a_json_object_is_refused(body, expected):
    service = MedexExtractionService(CONFIG, opener=RecordingOpener(body))

    with pytest.raises(ExtractionServiceError, match=expected):
        service.submit(document())
