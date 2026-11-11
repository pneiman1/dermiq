"""The shapes invoice intake moves around: document in, record out.

Money is :class:`~decimal.Decimal` throughout, parsed from the string or number
the service sent. Invoice totals are the input to true margin per service, and
a float sum of a hundred line items drifts in the fourth decimal place — enough to make a
lines-vs-total check fail on a perfectly good invoice, which would park real
cost in review for no reason.

A line item is stored against a **supplier** and a **period** (``YYYY-MM``).
The period is the accounting month the cost belongs to: taken from the invoice
date the service extracted, unless the document declares one explicitly, which
is how an invoice that arrives late still books to the month it was posted in.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

Payload = dict[str, Any]

#: Accounting period, year and month. Not a day: cost lands monthly.
PERIOD_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")

#: How far the line items may sum away from the invoice's own total before the
#: invoice is held for review. One cent, so penny rounding on a tax line passes
#: and a dropped or doubled line item does not.
TOTAL_TOLERANCE = Decimal("0.01")


class InvoiceIntegrityError(RuntimeError):
    """A service payload could not be turned into a landable invoice record.

    Raised rather than logged, and raised *before* anything is written: an
    invoice the client cannot read is a failed intake, not a partial one. Note
    the difference from a flagged extraction — that is a perfectly readable
    result the service is unsure about, and it lands pending (see
    :class:`InvoiceStatus`).
    """


class JobStatus(StrEnum):
    """Status of an extraction job, as reported by the service."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


#: Statuses that end the poll loop. Anything else means "ask again".
TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.NEEDS_REVIEW, JobStatus.FAILED}
)


class InvoiceStatus(StrEnum):
    """State a landed invoice is in.

    Only ``EXTRACTED`` feeds the cost model. The other two are stored so the
    arrival is auditable, and filtered out of every cost query — see
    :meth:`dermiq.invoices.store.InvoiceStore.line_items_for_cost_model`.
    """

    #: Clean: the service was confident and the lines add up. Counts as cost.
    EXTRACTED = "extracted"
    #: Flagged by the service, or failed a landing check here. Awaits a human.
    PENDING_REVIEW = "pending_review"
    #: A second document for an invoice number already landed. Counted once.
    DUPLICATE = "duplicate"


def accounting_period(value: date | datetime | str) -> str:
    """Return the ``YYYY-MM`` accounting period for a date or ISO date string."""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            raise InvoiceIntegrityError(
                f"invoice date {value!r} is not an ISO date; cannot tell which "
                "accounting period this cost belongs to"
            ) from None
    return f"{value.year:04d}-{value.month:02d}"


def _money(value: Any, *, field_name: str, context: str) -> Decimal:
    """Parse a monetary or quantity field into Decimal, via str to avoid float drift."""
    if value is None or value == "":
        raise InvoiceIntegrityError(f"{context}: {field_name} is missing")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InvoiceIntegrityError(
            f"{context}: {field_name}={value!r} is not a number"
        ) from None


@dataclass(frozen=True)
class InvoiceDocument:
    """A supplier invoice as it arrives: bytes, plus who it came from.

    ``period`` is optional and overrides the period derived from the extracted
    invoice date. ``fingerprint`` is what duplicate detection keys on before the
    document is ever sent, so re-submitting the same file costs no service call.
    """

    supplier_id: str
    filename: str
    content: bytes
    period: str | None = None
    content_type: str = "application/pdf"

    def __post_init__(self) -> None:
        if not self.supplier_id:
            raise InvoiceIntegrityError(
                f"document {self.filename!r} names no supplier; a line item with no "
                "supplier cannot be attributed to a cost"
            )
        if not self.content:
            raise InvoiceIntegrityError(f"document {self.filename!r} is empty")
        if self.period is not None and not PERIOD_RE.match(self.period):
            raise InvoiceIntegrityError(
                f"document {self.filename!r} declares period {self.period!r}; "
                "expected YYYY-MM"
            )

    @property
    def fingerprint(self) -> str:
        """Content hash, scoped to the supplier.

        Scoped because two suppliers can legitimately send byte-identical
        documents (the same boilerplate credit note, say), and those are two
        costs. The same bytes from the same supplier are one.
        """
        digest = hashlib.sha256()
        digest.update(self.supplier_id.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(self.content)
        return digest.hexdigest()


@dataclass(frozen=True)
class InvoiceLineItem:
    """One costed line of a supplier invoice."""

    line_number: int
    description: str
    quantity: Decimal
    unit: str
    unit_cost: Decimal
    total_cost: Decimal
    gl_account_code: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, context: str) -> InvoiceLineItem:
        if not isinstance(payload, Mapping):
            raise InvoiceIntegrityError(f"{context}: line item is not an object")
        line_number = payload.get("line_number")
        if not isinstance(line_number, int):
            raise InvoiceIntegrityError(
                f"{context}: line_number={line_number!r} is not an integer"
            )
        where = f"{context} line {line_number}"
        description = str(payload.get("description") or "").strip()
        if not description:
            raise InvoiceIntegrityError(f"{where}: description is empty")
        return cls(
            line_number=line_number,
            description=description,
            quantity=_money(payload.get("quantity"), field_name="quantity", context=where),
            unit=str(payload.get("unit") or "").strip(),
            unit_cost=_money(payload.get("unit_cost"), field_name="unit_cost", context=where),
            total_cost=_money(payload.get("total_cost"), field_name="total_cost", context=where),
            gl_account_code=(
                str(payload["gl_account_code"]) if payload.get("gl_account_code") else None
            ),
        )


@dataclass(frozen=True)
class ExtractionResult:
    """A terminal extraction job, parsed off the service's response envelope.

    ``flagged`` and ``review_reasons`` carry the service's own verdict. The
    client adds its reasons to them at landing time; it never clears them.
    """

    job_id: str
    status: JobStatus
    supplier_id: str
    invoice_number: str
    invoice_date: str
    currency: str
    total: Decimal
    line_items: tuple[InvoiceLineItem, ...]
    flagged: bool = False
    review_reasons: tuple[str, ...] = ()
    confidence: float | None = None
    document_fingerprint: str | None = None

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, Any], *, document: InvoiceDocument
    ) -> ExtractionResult:
        """Parse a terminal service response. Raises rather than guess a field.

        Every ``raise`` here happens before the store is touched, which is what
        makes an unreadable response leave no record behind.
        """
        if not isinstance(payload, Mapping):
            raise InvoiceIntegrityError(
                f"extraction response for {document.filename!r} is not an object, got "
                f"{type(payload).__name__}"
            )
        job_id = str(payload.get("job_id") or "")
        context = f"extraction job {job_id or '<unknown>'} ({document.filename})"

        status = read_job_status(payload, context=context)
        if status not in TERMINAL_JOB_STATUSES:
            raise InvoiceIntegrityError(f"{context}: job is still {status}, nothing to parse")
        if status is JobStatus.FAILED:
            raise InvoiceIntegrityError(
                f"{context}: service reported failure: {payload.get('error') or 'no reason given'}"
            )

        invoice = payload.get("invoice")
        if not isinstance(invoice, Mapping):
            raise InvoiceIntegrityError(f"{context}: response carries no invoice object")

        supplier_id = str(invoice.get("supplier_id") or document.supplier_id)
        if supplier_id != document.supplier_id:
            # The service reading a different supplier off the page than the one
            # the document was filed under is a mis-filing, not a review note:
            # landing it would charge one supplier's cost to another.
            raise InvoiceIntegrityError(
                f"{context}: extracted supplier {supplier_id!r} does not match the "
                f"document's supplier {document.supplier_id!r}"
            )

        invoice_number = str(invoice.get("invoice_number") or "").strip()
        if not invoice_number:
            raise InvoiceIntegrityError(
                f"{context}: no invoice number; without it the same invoice cannot "
                "be recognised on a second submission"
            )

        # An empty list here is a bug in the service, not an absent review: it
        # must not be allowed to coerce quietly into "nothing was flagged".
        review = {} if payload.get("review") is None else payload["review"]
        if not isinstance(review, Mapping):
            raise InvoiceIntegrityError(
                f"{context}: review is not an object, got {type(review).__name__}"
            )
        reasons = tuple(str(reason) for reason in (review.get("reasons") or ()))
        flagged = bool(review.get("flagged")) or status is JobStatus.NEEDS_REVIEW

        lines = invoice.get("line_items")
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)):
            raise InvoiceIntegrityError(f"{context}: line_items is not a list")

        confidence = invoice_confidence(payload, context=context)

        return cls(
            job_id=job_id,
            status=status,
            supplier_id=supplier_id,
            invoice_number=invoice_number,
            invoice_date=str(invoice.get("invoice_date") or ""),
            currency=str(invoice.get("currency") or "USD"),
            total=_money(invoice.get("total"), field_name="total", context=context),
            line_items=tuple(
                InvoiceLineItem.from_payload(line, context=context) for line in lines
            ),
            flagged=flagged,
            review_reasons=reasons,
            confidence=confidence,
            document_fingerprint=(
                str(payload["document_fingerprint"])
                if payload.get("document_fingerprint")
                else None
            ),
        )

    @property
    def line_total(self) -> Decimal:
        return sum((line.total_cost for line in self.line_items), start=Decimal("0"))


def read_job_status(payload: Mapping[str, Any], *, context: str) -> JobStatus:
    """Read ``status`` off a service response, refusing a status we do not know.

    An unknown status is not treated as pending: polling forever on a word the
    service added in a later version would read as a hung intake.
    """
    raw = str(payload.get("status") or "").strip().lower()
    try:
        return JobStatus(raw)
    except ValueError:
        raise InvoiceIntegrityError(
            f"{context}: unknown job status {raw!r}; known: "
            f"{sorted(status.value for status in JobStatus)}"
        ) from None


def invoice_confidence(payload: Mapping[str, Any], *, context: str) -> float | None:
    confidence = payload.get("confidence")
    if confidence is None:
        return None
    try:
        return float(confidence)
    except (TypeError, ValueError):
        raise InvoiceIntegrityError(
            f"{context}: confidence={confidence!r} is not a number"
        ) from None


@dataclass(frozen=True)
class InvoiceRecord:
    """A landed invoice: line items, keyed by supplier and period, plus its status.

    Written once, in full. Nothing in this package mutates a record in place —
    which is how a timed-out intake leaves no partial row to clean up.
    """

    fingerprint: str
    supplier_id: str
    period: str
    invoice_number: str
    status: InvoiceStatus
    line_items: tuple[InvoiceLineItem, ...]
    invoice_date: str
    currency: str
    total: Decimal
    job_id: str
    landed_at: datetime
    document_filename: str
    review_reasons: tuple[str, ...] = ()
    confidence: float | None = None
    #: Set on a DUPLICATE record: the fingerprint of the copy that did count.
    duplicate_of: str | None = None
    #: Service and client metadata worth keeping next to the numbers.
    service_mode: str = "stub"
    tenant: str = ""

    @property
    def counts_as_cost(self) -> bool:
        """Whether this record's line items belong in the cost model."""
        return self.status is InvoiceStatus.EXTRACTED

    @property
    def invoice_key(self) -> tuple[str, str]:
        """Supplier plus invoice number: the identity an invoice is counted once by."""
        return (self.supplier_id, self.invoice_number)

    @property
    def line_total(self) -> Decimal:
        return sum((line.total_cost for line in self.line_items), start=Decimal("0"))
