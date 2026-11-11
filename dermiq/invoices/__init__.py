"""Document intake — the cost side of the practice's margin.

True margin per service, cost per treatment and the injectable consumption
model all need the documents that say what was charged and what was collected,
and those arrive as PDFs and scans rather than as rows. An extraction service
turns the document into line items; this package is the **client** of that
service and nothing more. No extraction happens here (see
:mod:`dermiq.invoices.service` for the seam, and the module docstring there for
the wire contract this client expects).

The path, end to end::

    document -> service.submit()  -> job id
             -> service.result()  -> poll until terminal
             -> ExtractionResult  -> parse + land as an InvoiceRecord
             -> InvoiceStore      -> line items keyed by supplier and period

Three rules shape the implementation, and each has a test behind it:

* **Nothing lands until the whole result is in hand.** A timeout or a service
  error leaves the store exactly as it was, so the document can be re-submitted
  without reconciling a half-written invoice.
* **Flagged extractions land pending.** A result the service marked for review —
  or one whose lines do not add up to its own total — is stored with
  ``InvoiceStatus.PENDING_REVIEW`` and is invisible to
  :meth:`~dermiq.invoices.store.InvoiceStore.line_items_for_cost_model`. Margin
  per service is never moved by a number nobody checked.
* **A document is counted once.** The same document re-submitted is a no-op; a
  second document for an invoice number already landed is stored as
  ``InvoiceStatus.DUPLICATE`` — auditable, and out of the cost model.

Default wiring is local: with no environment set, ``InvoiceIntake()`` runs
against :class:`~dermiq.invoices.service.StubExtractionService`, so the tests
and a demo need nothing switched on. ``INVOICE_SERVICE_MODE=medex`` with an
``INVOICE_SERVICE_URL`` points it at the deployed extraction service instead.
"""
from __future__ import annotations

from dermiq.invoices.config import (
    InvoiceConfigError,
    InvoiceServiceConfig,
    load_service_config,
    required_variables,
)
from dermiq.invoices.intake import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    InvoiceIntake,
)
from dermiq.invoices.service import (
    ExtractionFailedError,
    ExtractionService,
    ExtractionServiceError,
    ExtractionTimeoutError,
    MedexExtractionService,
    StubExtractionService,
    build_extraction_service,
)
from dermiq.invoices.store import (
    DuplicateInvoiceError,
    InMemoryInvoiceStore,
    InvoiceStore,
)
from dermiq.invoices.types import (
    TERMINAL_JOB_STATUSES,
    ExtractionResult,
    InvoiceDocument,
    InvoiceIntegrityError,
    InvoiceLineItem,
    InvoiceRecord,
    InvoiceStatus,
    JobStatus,
    accounting_period,
)

__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DuplicateInvoiceError",
    "ExtractionFailedError",
    "ExtractionResult",
    "ExtractionService",
    "ExtractionServiceError",
    "ExtractionTimeoutError",
    "InMemoryInvoiceStore",
    "InvoiceConfigError",
    "InvoiceDocument",
    "InvoiceIntake",
    "InvoiceIntegrityError",
    "InvoiceLineItem",
    "InvoiceRecord",
    "InvoiceServiceConfig",
    "InvoiceStatus",
    "InvoiceStore",
    "JobStatus",
    "MedexExtractionService",
    "StubExtractionService",
    "TERMINAL_JOB_STATUSES",
    "accounting_period",
    "build_extraction_service",
    "load_service_config",
    "required_variables",
]
