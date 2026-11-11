"""Intake: hand a document to the extraction service and land what comes back.

The order of operations is the whole design. Read it as a sentence:

1. **Has this document already landed?** Keyed on the content fingerprint. If so
   return the record that landed and make no service call — a re-sent document
   costs nothing and counts once.
2. **POST it.** One call, one job id.
3. **Poll until terminal, or until the deadline.** A deadline hit raises
   :class:`~dermiq.invoices.service.ExtractionTimeoutError`. Nothing has been
   written at this point and nothing will be: the document is still unknown to
   the store, so re-submitting it later is a clean first attempt rather than a
   reconciliation.
4. **Parse the result.** Anything unreadable raises
   :class:`~dermiq.invoices.types.InvoiceIntegrityError`, still before any write.
5. **Decide the status.** Flagged by the service, or failing one of the landing
   checks below, lands ``PENDING_REVIEW``. An invoice number already counted
   lands ``DUPLICATE``. Otherwise ``EXTRACTED``.
6. **Write once.** A single atomic :meth:`~dermiq.invoices.store.InvoiceStore.add`.

The landing checks in step 5 are not extraction — they are arithmetic on what
the service returned, the three ways a confident-looking result still must not
move true margin per service:

* no line items at all,
* line items that do not sum to the invoice's own total (beyond a cent),
* no invoice date, so the cost has no period to land in.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from platform_core.utils.logging import get_logger

from dermiq.invoices.config import InvoiceServiceConfig, load_service_config
from dermiq.invoices.service import (
    ExtractionFailedError,
    ExtractionService,
    ExtractionTimeoutError,
    build_extraction_service,
)
from dermiq.invoices.store import InMemoryInvoiceStore, InvoiceStore
from dermiq.invoices.types import (
    TERMINAL_JOB_STATUSES,
    TOTAL_TOLERANCE,
    ExtractionResult,
    InvoiceDocument,
    InvoiceIntegrityError,
    InvoiceRecord,
    InvoiceStatus,
    JobStatus,
    Payload,
    accounting_period,
    read_job_status,
)

log = get_logger(__name__)

#: How long one document may spend in extraction before intake gives up.
DEFAULT_TIMEOUT_SECONDS = 120.0
#: Gap between polls. Extraction is seconds-to-minutes work, not milliseconds.
DEFAULT_POLL_INTERVAL_SECONDS = 2.0

#: Review reasons this client adds. The service's own reasons are kept as sent.
NO_LINE_ITEMS = "no_line_items"
TOTAL_MISMATCH = "line_items_do_not_sum_to_total"
NO_INVOICE_DATE = "no_invoice_date"
DUPLICATE_INVOICE = "duplicate_invoice_number"


class InvoiceIntake:
    """Client for the extraction service, with the landing rules attached.

    Everything is draft and everything has a local default, so
    ``InvoiceIntake()`` is a working offline intake: the stub service, an
    in-memory store, and the real clock. ``clock``/``sleep`` are injected for the
    same reason the transport is — a test should be able to blow through a
    two-minute deadline without waiting two minutes.
    """

    def __init__(
        self,
        service: ExtractionService | None = None,
        store: InvoiceStore | None = None,
        *,
        config: InvoiceServiceConfig | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be > 0")
        # The config is only read when it is needed: an unconfigured process
        # building a stub-backed intake must not trip over a missing variable.
        self.config = config if config is not None else (
            None if service is not None else load_service_config()
        )
        self.service = service if service is not None else build_extraction_service(self.config)
        self.store = store if store is not None else InMemoryInvoiceStore()
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._now = now

    @property
    def tenant(self) -> str:
        return self.config.tenant if self.config is not None else ""

    def submit(self, document: InvoiceDocument) -> InvoiceRecord:
        """Run one document through extraction and land it. Returns the record.

        Raises :class:`~dermiq.invoices.service.ExtractionTimeoutError`,
        :class:`~dermiq.invoices.service.ExtractionFailedError` or
        :class:`~dermiq.invoices.types.InvoiceIntegrityError` without having
        written anything.
        """
        already_landed = self.store.get(document.fingerprint)
        if already_landed is not None:
            log.info(
                "invoice_already_landed",
                supplier_id=document.supplier_id,
                filename=document.filename,
                invoice_number=already_landed.invoice_number,
                status=already_landed.status.value,
                reason="same document submitted again; not sent for extraction",
            )
            return already_landed

        job_id = self.service.submit(document)
        payload = self._poll(job_id, document)
        result = ExtractionResult.from_payload(payload, document=document)
        return self.store.add(self._record_for(document, result))

    def _poll(self, job_id: str, document: InvoiceDocument) -> Payload:
        """Ask after the job until it is terminal or the deadline passes.

        Polls at least once (a job that is already done costs one call), and
        never sleeps past the deadline.
        """
        started = self._clock()
        polls = 0
        while True:
            payload = self.service.result(job_id)
            polls += 1
            context = f"extraction job {job_id} ({document.filename})"
            if not isinstance(payload, Mapping):
                raise InvoiceIntegrityError(
                    f"{context}: poll returned {type(payload).__name__}, which is not an "
                    "object; the response envelope is a JSON object (see "
                    "dermiq.invoices.service)"
                )
            status = read_job_status(payload, context=context)
            if status in TERMINAL_JOB_STATUSES:
                log.info(
                    "invoice_extraction_terminal",
                    job_id=job_id,
                    status=status.value,
                    polls=polls,
                )
                if status is JobStatus.FAILED:
                    raise ExtractionFailedError(
                        f"{context}: service reported failure: "
                        f"{payload.get('error') or 'no reason given'}"
                    )
                return payload

            elapsed = self._clock() - started
            remaining = self.timeout_seconds - elapsed
            if remaining <= 0:
                # Deliberately the last thing that happens for this document:
                # nothing has been written, so there is no partial record to
                # unwind and the next submission starts clean.
                log.warning(
                    "invoice_extraction_timeout",
                    job_id=job_id,
                    supplier_id=document.supplier_id,
                    filename=document.filename,
                    polls=polls,
                    timeout_seconds=self.timeout_seconds,
                )
                raise ExtractionTimeoutError(
                    f"{context}: still {status.value} after {polls} poll(s) and "
                    f"{elapsed:.1f}s (deadline {self.timeout_seconds:.1f}s); nothing was "
                    "stored, re-submit the document to try again"
                )
            self._sleep(min(self.poll_interval_seconds, remaining))

    def _record_for(self, document: InvoiceDocument, result: ExtractionResult) -> InvoiceRecord:
        """Decide status and period, and assemble the record. Writes nothing."""
        reasons = list(result.review_reasons)
        if result.flagged and not reasons:
            # The service flagged it without saying why; losing that is worse
            # than an unhelpful reason.
            reasons.append("flagged_by_extraction_service")

        if not result.line_items:
            reasons.append(NO_LINE_ITEMS)
        elif abs(result.line_total - result.total) > TOTAL_TOLERANCE:
            reasons.append(
                f"{TOTAL_MISMATCH}: lines {result.line_total} vs total {result.total}"
            )

        period = document.period
        if period is None and result.invoice_date:
            period = accounting_period(result.invoice_date)
        landed_at = self._now()
        if period is None:
            # Undated and nobody declared a period. It still lands — pending, and
            # filed under the month it arrived in, which is where a human will
            # look for it. It cannot reach the cost model from there.
            reasons.append(NO_INVOICE_DATE)
            period = accounting_period(landed_at)

        status = InvoiceStatus.PENDING_REVIEW if reasons else InvoiceStatus.EXTRACTED

        duplicate_of: str | None = None
        counted = self.store.find_invoice(result.supplier_id, result.invoice_number)
        if counted is not None:
            # A second document for an invoice that already counts. Keep it —
            # a re-scan or a corrected copy is worth having on file — but it is
            # not cost, and nothing downstream will sum it.
            duplicate_of = counted.fingerprint
            status = InvoiceStatus.DUPLICATE
            reasons.append(f"{DUPLICATE_INVOICE}: already landed as {counted.fingerprint[:12]}")
            log.info(
                "invoice_duplicate",
                supplier_id=result.supplier_id,
                invoice_number=result.invoice_number,
                counted_fingerprint=counted.fingerprint,
                filename=document.filename,
            )

        return InvoiceRecord(
            fingerprint=document.fingerprint,
            supplier_id=result.supplier_id,
            period=period,
            invoice_number=result.invoice_number,
            status=status,
            line_items=result.line_items,
            invoice_date=result.invoice_date,
            currency=result.currency,
            total=result.total,
            job_id=result.job_id,
            landed_at=landed_at,
            document_filename=document.filename,
            review_reasons=tuple(reasons),
            confidence=result.confidence,
            duplicate_of=duplicate_of,
            service_mode=self.service.mode,
            tenant=self.tenant,
        )
