"""The extraction-service seam: hand over a document, read the result.

Extraction itself is somebody else's job — this repo is a client, and nothing
here reads a PDF. What is defined here is the wire contract the client expects,
because the stub and the real service have to agree on it:

    {
      "job_id": "job-1",
      "status": "pending" | "succeeded" | "needs_review" | "failed",
      "error": null,                       # set when status is failed
      "document_fingerprint": "<sha256>",  # echoed back, optional
      "confidence": 0.98,                  # optional
      "review": {"flagged": false, "reasons": []},
      "invoice": {
        "supplier_id": "sup_allergan_aesthetics",
        "invoice_number": "CLM-2026-66635",
        "invoice_date": "2026-08-27",
        "currency": "USD",
        "total": "51407.62",
        "line_items": [
          {"line_number": 1, "description": "ARTHROCENTESIS MAJOR JOINT",
           "quantity": "3", "unit": "service", "unit_cost": "119.30",
           "total_cost": "357.90", "gl_account_code": "20610"}
        ]
      }
    }

:mod:`dermiq.invoices.types` parses exactly that, and the whole suite tests
against it, so the contract does not move. A service with a different shape
gets an adapter — which is what :class:`MedexExtractionService` is.

Two implementations ship:

* :class:`StubExtractionService` — the default. Local, offline, no credential.
  It *replays* a canned extraction envelope carried in the document itself
  rather than extracting anything, which is what lets the tests and a demo run
  with nothing else switched on.
* :class:`MedexExtractionService` — the real path, against the deployed medex
  document-extraction service. See its docstring for the two places medex's
  shape differs from the contract above and how each is bridged.

Both over stdlib ``urllib``. No new dependency: the base install carries no
HTTP client, and invoice intake is not a reason to add one.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from platform_core.utils.logging import get_logger

from dermiq.invoices.config import (
    MEDEX_MODE,
    STUB_MODE,
    InvoiceConfigError,
    InvoiceServiceConfig,
    load_service_config,
)
from dermiq.invoices.types import InvoiceDocument, JobStatus, Payload

log = get_logger(__name__)

#: Tenant travels as a header, not a query string: it is routing, and it should
#: not end up in the service's access log alongside a document id.
TENANT_HEADER = "X-Tenant-Id"

#: Socket timeout for a single HTTP call. The *overall* deadline is the intake's
#: (see dermiq.invoices.intake); this one only stops one request hanging forever.
REQUEST_TIMEOUT_SECONDS = 30.0

#: Reason attached to a stub job whose document is not a canned envelope. A real
#: service says much the same thing about a scan it could not read.
UNREADABLE_REASON = "unreadable_document"


class ExtractionServiceError(RuntimeError):
    """The extraction service could not be reached, or answered unusably."""


class ExtractionTimeoutError(ExtractionServiceError):
    """The extraction did not reach a terminal state inside the deadline.

    Carries no record with it, and leaves none behind: the intake writes only
    after a terminal result is parsed (see
    :meth:`dermiq.invoices.intake.InvoiceIntake.submit`).
    """


class ExtractionFailedError(ExtractionServiceError):
    """The service reached a terminal state and that state was failure."""


class ExtractionService(ABC):
    """Transport seam. Two methods: hand over a document, ask after the job."""

    #: Short mode name, stamped on the records this service's results produce.
    mode: str = "unknown"

    @abstractmethod
    def submit(self, document: InvoiceDocument) -> str:
        """Hand over the document. Return the service's job id."""

    @abstractmethod
    def result(self, job_id: str) -> Payload:
        """Return the job's current response envelope (see the module docstring)."""


class StubExtractionService(ExtractionService):
    """Local stand-in for the extraction service. Replays, does not extract.

    The document's bytes *are* the canned envelope: a JSON object holding the
    ``invoice`` the service would have read off the page, optionally with a
    ``review`` block. Anything that is not such an object — a real PDF, say —
    comes back flagged for review with reason ``unreadable_document``, which is
    the honest answer for a stub handed a document it cannot read, and keeps a
    demo against real files from inventing cost.

    ``polls_until_ready`` makes the job take that many polls to go terminal, so
    the poll loop and its deadline are exercised without a service behind it.
    Submissions are recorded in ``submissions`` so a caller (or a test) can see
    that a duplicate document was never sent twice.
    """

    mode = STUB_MODE

    def __init__(self, *, polls_until_ready: int = 0) -> None:
        if polls_until_ready < 0:
            raise ValueError("polls_until_ready must be >= 0")
        self.polls_until_ready = polls_until_ready
        self.submissions: list[InvoiceDocument] = []
        self.polls: list[str] = []
        self._jobs: dict[str, Payload] = {}
        self._poll_counts: dict[str, int] = {}

    def submit(self, document: InvoiceDocument) -> str:
        job_id = f"stub-job-{len(self.submissions) + 1}"
        self.submissions.append(document)
        self._jobs[job_id] = self._envelope(job_id, document)
        self._poll_counts[job_id] = 0
        log.info(
            "invoice_stub_submitted",
            job_id=job_id,
            supplier_id=document.supplier_id,
            filename=document.filename,
        )
        return job_id

    def result(self, job_id: str) -> Payload:
        if job_id not in self._jobs:
            raise ExtractionServiceError(f"stub has no job {job_id!r}")
        self.polls.append(job_id)
        self._poll_counts[job_id] += 1
        if self._poll_counts[job_id] <= self.polls_until_ready:
            return {"job_id": job_id, "status": JobStatus.PENDING.value}
        return json.loads(json.dumps(self._jobs[job_id]))  # a copy; callers may not mutate

    def _envelope(self, job_id: str, document: InvoiceDocument) -> Payload:
        canned = self._read_canned(document)
        if canned is None:
            return {
                "job_id": job_id,
                "status": JobStatus.NEEDS_REVIEW.value,
                "document_fingerprint": document.fingerprint,
                "review": {
                    "flagged": True,
                    "reasons": [UNREADABLE_REASON],
                },
                # Enough of an invoice to be filed and found again, and not one
                # line item: there is nothing here anybody should cost.
                "invoice": {
                    "supplier_id": document.supplier_id,
                    "invoice_number": document.filename,
                    "invoice_date": "",
                    "currency": "USD",
                    "total": "0",
                    "line_items": [],
                },
            }

        invoice = dict(canned.get("invoice") or canned)
        invoice.setdefault("supplier_id", document.supplier_id)
        envelope: Payload = {
            "job_id": job_id,
            "status": str(canned.get("status") or JobStatus.SUCCEEDED.value),
            "document_fingerprint": document.fingerprint,
            "invoice": invoice,
        }
        if "review" in canned:
            envelope["review"] = canned["review"]
        if canned.get("confidence") is not None:
            envelope["confidence"] = canned["confidence"]
        if canned.get("error") is not None:
            envelope["error"] = canned["error"]
        return envelope

    @staticmethod
    def _read_canned(document: InvoiceDocument) -> dict[str, Any] | None:
        try:
            canned = json.loads(document.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return canned if isinstance(canned, dict) else None


# --------------------------------------------------------------------------
# medex
# --------------------------------------------------------------------------

#: Where a demo upload goes, and where its result is read back from. The demo
#: surface rather than POST /documents, and not as a shortcut: the real route
#: takes a `source_path` on the *service's* filesystem, which a caller in
#: another datacentre has no way to satisfy. /demo/documents takes the bytes.
SUBMIT_PATH = "/demo/documents"
RESULT_PATH = "/demo/documents/{job_id}"

#: Medex reports no currency. The practice's ledger is USD and so is every
#: document in medex's corpus; a guessed currency symbol would be worse than a
#: stated assumption.
ASSUMED_CURRENCY = "USD"

#: Unit on every line. Medex counts procedures, which are billed per service
#: performed — there is no pounds-or-each distinction to carry.
SERVICE_UNIT = "service"

#: Review reasons this adapter adds, for the two fields medex can leave blank
#: on a document it could not read.
NO_CLAIM_NUMBER = "no_claim_number_extracted"
NO_SERVICE_DATE = "no_service_date_extracted"


class MedexExtractionService(ExtractionService):
    """Adapter onto the deployed medex document-extraction service.

    Medex reads billing packets — a provider, a claim number, a service date
    range and a table of procedures with units and amounts. For a cosmetic
    dermatology practice that is the document that decides what was actually
    collected, which is the input to true margin per service. It is the same
    job the sibling verticals' supplier invoices do, on the document type this
    vertical actually receives, so it lands through the same intake and the
    same three landing rules.

    TWO PLACES THE SHAPES DIFFER.

    *There is no job to poll.* Medex extracts inside the POST and answers 201
    with the finished document. `submit` therefore keeps the envelope it got
    and `result` serves it, re-fetching only if asked for a token it does not
    hold. The poll loop upstairs is not bypassed — it runs, sees a terminal
    status on its first call, and returns. That is the honest reading of a
    synchronous service, and it leaves the deadline and the timeout path
    exactly as they are for a service that is not.

    *The field names are medex's.* The mapping, and why each:

        claim_number      -> invoice_number   the identity an invoice is counted
                                              once by. Falls back to the
                                              filename when medex extracted
                                              none, which lands the document
                                              pending rather than raising —
                                              same as the stub does for a scan
                                              it cannot read.
        date_range_end    -> invoice_date     the end of the service period is
                                              the month the cost belongs to.
                                              Falls back to the start date.
        total_billed      -> total            what was charged. `total_paid` is
                                              deliberately not used: the cost
                                              model wants the billed amount,
                                              and the two differ by the
                                              adjustment, which is a separate
                                              fact.
        line_items[]      -> line_items[]     description or CPT for the text,
                                              `units` for quantity, `billed`
                                              for the line total, CPT for the
                                              GL code. `unit_cost` is derived —
                                              see `_line_items`.
        flags / auto_ok   -> review           any rule flag, or auto_ok false,
                                              is a flagged extraction. Medex's
                                              own flag strings are carried
                                              through unchanged.
        min_confidence    -> confidence       the worst field on the document,
                                              which is the one worth knowing.

    `provider_name` is read but not mapped onto `supplier_id`. Medex extracts a
    name off the page; a supplier id is a key in this warehouse, and the two
    are not the same thing. The document's own `supplier_id` — chosen by
    whoever filed it — is authoritative, which is also what keeps
    `ExtractionResult.from_payload`'s mis-filing check meaningful.
    """

    mode = MEDEX_MODE

    def __init__(
        self,
        config: InvoiceServiceConfig,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if not config.url or not config.tenant:
            raise InvoiceConfigError(
                "MedexExtractionService needs both a URL and a tenant; "
                f"got url={config.url!r} tenant={config.tenant!r}"
            )
        self.config = config
        self._opener = opener
        self._timeout = timeout
        #: token -> the envelope the POST already returned. Not a cache in
        #: front of a slow service: it is where the one and only answer lives.
        self._envelopes: dict[str, Payload] = {}
        #: The document each token was for, so a re-fetch can be translated.
        self._documents: dict[str, InvoiceDocument] = {}

    def submit(self, document: InvoiceDocument) -> str:
        payload = self._call(
            SUBMIT_PATH,
            data=document.content,
            headers={"Content-Type": document.content_type},
            method="POST",
        )
        token = str(payload.get("doc_hash") or "")
        if not token:
            raise ExtractionServiceError(
                f"medex accepted {document.filename!r} but returned no doc_hash: "
                f"{sorted(payload)}"
            )
        self._documents[token] = document
        self._envelopes[token] = self.translate(payload, document=document)
        log.info(
            "invoice_submitted",
            job_id=token,
            supplier_id=document.supplier_id,
            tenant=self.config.tenant,
            service="medex",
        )
        return token

    def result(self, job_id: str) -> Payload:
        held = self._envelopes.get(job_id)
        if held is not None:
            return json.loads(json.dumps(held))  # a copy; callers may not mutate

        document = self._documents.get(job_id)
        if document is None:
            raise ExtractionServiceError(
                f"no document on record for medex token {job_id!r}; "
                "result() is only callable for a token submit() returned"
            )
        return self.translate(
            self._call(RESULT_PATH.format(job_id=job_id), method="GET"), document=document
        )

    # -- translation --------------------------------------------------------

    @classmethod
    def translate(cls, view: Mapping[str, Any], *, document: InvoiceDocument) -> Payload:
        """One medex document view -> one response envelope. Pure; no I/O.

        A classmethod because it is the part worth testing without a socket,
        and the part that breaks if medex's view ever changes shape.
        """
        if not isinstance(view, Mapping):
            raise ExtractionServiceError(
                f"medex returned {type(view).__name__}, expected a JSON object"
            )

        token = str(view.get("doc_hash") or "")
        # `or {}` would be wrong here: an empty list is a bug in the service,
        # and must not coerce quietly into "this document has no fields".
        fields = {} if view.get("fields") is None else view["fields"]
        if not isinstance(fields, Mapping):
            raise ExtractionServiceError(
                f"medex token {token!r}: fields is not an object, got "
                f"{type(fields).__name__}"
            )

        reasons = [str(flag) for flag in (view.get("flags") or ())]

        invoice_number = _field_value(fields, "claim_number")
        if not invoice_number:
            # Not an error. A packet medex could not read still has to be
            # filed, found again and reviewed by a person; refusing it here
            # would turn an unreadable scan into a failed intake.
            invoice_number = document.filename
            reasons.append(NO_CLAIM_NUMBER)

        invoice_date = _field_value(fields, "date_range_end") or _field_value(
            fields, "date_range_start"
        )
        if not invoice_date:
            reasons.append(NO_SERVICE_DATE)

        flagged = bool(reasons) or view.get("auto_ok") is False

        return {
            "job_id": token,
            # Medex has no pending state on this route: it extracts inside the
            # POST, so whatever came back is already the final answer.
            "status": (
                JobStatus.NEEDS_REVIEW.value if flagged else JobStatus.SUCCEEDED.value
            ),
            "document_fingerprint": document.fingerprint,
            "confidence": view.get("min_confidence"),
            "review": {"flagged": flagged, "reasons": reasons},
            "invoice": {
                # The document's, not the extracted provider_name — see the
                # class docstring.
                "supplier_id": document.supplier_id,
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "currency": ASSUMED_CURRENCY,
                "total": _decimal_or_zero(view.get("total_billed")),
                "line_items": cls._line_items(view.get("line_items") or (), token=token),
            },
        }

    @staticmethod
    def _line_items(rows: Any, *, token: str) -> list[Payload]:
        """Medex procedure rows -> invoice line items.

        `unit_cost` is derived rather than read, because medex does not carry
        one: it records units and the billed amount for the line. The division
        is quantized to the cent the practice is actually charged in, and the
        line's own `total_cost` stays the billed figure medex extracted — so
        the lines-sum-to-total check upstairs tests medex's arithmetic and not
        this adapter's rounding. A zero- or no-unit line gets its billed amount
        as the unit cost, which is what one of something costs.
        """
        if isinstance(rows, (str, bytes)) or not hasattr(rows, "__iter__"):
            raise ExtractionServiceError(
                f"medex token {token!r}: line_items is not a list"
            )

        items: list[Payload] = []
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                raise ExtractionServiceError(
                    f"medex token {token!r} line {index}: not an object"
                )
            cpt = str(row.get("cpt") or "").strip()
            description = str(row.get("description") or "").strip() or cpt
            if not description:
                # Neither a description nor a CPT code. The line is a cost with
                # nothing attached to it; naming the position is the most this
                # adapter honestly knows.
                description = f"unlabelled line {index}"
            billed = _decimal(row.get("billed")) or Decimal("0")
            quantity = _decimal(row.get("units")) or Decimal("1")
            unit_cost = (
                billed / quantity if quantity else billed
            ).quantize(Decimal("0.01"))
            items.append(
                {
                    "line_number": index,
                    "description": description,
                    "quantity": str(quantity),
                    "unit": SERVICE_UNIT,
                    "unit_cost": str(unit_cost),
                    "total_cost": str(billed),
                    "gl_account_code": cpt or None,
                }
            )
        return items

    # -- transport ---------------------------------------------------------

    def _call(
        self,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        method: str,
    ) -> Payload:
        url = f"{self.config.url}{path}"
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header(TENANT_HEADER, self.config.tenant)
        request.add_header("Accept", "application/json")
        for name, value in (headers or {}).items():
            request.add_header(name, value)

        try:
            with self._opener(request, timeout=self._timeout) as response:
                raw = response.read()
        except TimeoutError as exc:  # socket-level; the deadline is the intake's
            raise ExtractionTimeoutError(f"{method} {url} timed out: {exc}") from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ExtractionServiceError(
                f"{method} {url} returned HTTP {exc.code}: {detail}"
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, TimeoutError):
                raise ExtractionTimeoutError(f"{method} {url} timed out: {reason}") from exc
            raise ExtractionServiceError(f"{method} {url} failed: {reason}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionServiceError(f"{method} {url} returned non-JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ExtractionServiceError(
                f"{method} {url} returned {type(payload).__name__}, expected a JSON object"
            )
        return payload


def _field_value(fields: Mapping[str, Any], name: str) -> str:
    """One medex extracted field's value, or "" if it has none.

    Medex wraps every scalar as ``{"value": ..., "confidence": ...}``, and a
    field it could not read is present with a null value rather than absent.
    """
    field = fields.get(name)
    if isinstance(field, Mapping):
        return str(field.get("value") or "").strip()
    return str(field or "").strip()


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_or_zero(value: Any) -> str:
    """A total, as a string for the contract. Absent reads as zero.

    Zero rather than a raise: a document with no total is a document the intake
    holds for review (its lines will not sum to zero), which is where an
    unreadable packet belongs. Raising here would lose it instead.
    """
    parsed = _decimal(value)
    return str(parsed if parsed is not None else Decimal("0"))


def build_extraction_service(
    config: InvoiceServiceConfig | None = None,
    *,
    env: dict[str, str] | None = None,
) -> ExtractionService:
    """Build the service the environment asks for; the stub when it asks nothing.

    Defaulting to the stub rather than to an HTTP client pointed at nowhere is
    deliberate: an unconfigured intake should run locally and land nothing in a
    real system, not fail at import time or post a document into the void.
    """
    resolved = config if config is not None else load_service_config(env)
    if resolved.is_stub:
        return StubExtractionService()
    return MedexExtractionService(resolved)
