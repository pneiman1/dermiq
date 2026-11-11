"""Where landed invoices live, and the one query the cost model is allowed.

The store is deliberately an interface with an in-memory implementation behind
it. Invoice line items ultimately belong in the warehouse next to
``RAW_<TENANT>.TRANSACTIONS`` and ``INVENTORY_LOTS``, but the raw-layer type
map is not this task's to extend,
and an intake that needs live Snowflake credentials could not be demoed or
tested. So: one seam, one local implementation, and a warehouse-backed one later
with no change above this line.

Two guarantees the implementation owes the rest of the package:

* **Atomic add.** :meth:`InvoiceStore.add` either lands a whole record or
  changes nothing. There is no "create then fill in the line items" path, which
  is why an extraction that times out mid-intake leaves no partial row.
* **Counted once.** An invoice key (supplier plus invoice number) holds at most
  one cost-bearing record. A second one is rejected, and the intake lands it as
  :attr:`~dermiq.invoices.types.InvoiceStatus.DUPLICATE` instead.

The cost model reads :meth:`InvoiceStore.line_items_for_cost_model`, which only
ever returns line items from ``EXTRACTED`` records. A pending invoice is
readable through :meth:`InvoiceStore.pending`, by a human, on purpose.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from platform_core.utils.logging import get_logger

from dermiq.invoices.types import InvoiceLineItem, InvoiceRecord, InvoiceStatus

log = get_logger(__name__)


class DuplicateInvoiceError(RuntimeError):
    """An invoice already landed under this fingerprint or this invoice key."""


class InvoiceStore(ABC):
    """Storage seam for landed supplier invoices."""

    @abstractmethod
    def add(self, record: InvoiceRecord) -> InvoiceRecord:
        """Land a complete record. Atomic: either all of it, or nothing at all."""

    @abstractmethod
    def get(self, fingerprint: str) -> InvoiceRecord | None:
        """The record for a document fingerprint, if that document already landed."""

    @abstractmethod
    def find_invoice(self, supplier_id: str, invoice_number: str) -> InvoiceRecord | None:
        """The cost-bearing record for an invoice key, if one landed."""

    @abstractmethod
    def records(
        self,
        *,
        supplier_id: str | None = None,
        period: str | None = None,
        status: InvoiceStatus | None = None,
    ) -> tuple[InvoiceRecord, ...]:
        """Landed records, newest last, filtered by supplier, period and status."""

    def line_items_for_cost_model(
        self,
        *,
        supplier_id: str | None = None,
        period: str | None = None,
    ) -> tuple[InvoiceLineItem, ...]:
        """Line items that may be costed: ``EXTRACTED`` records only.

        The single door into the cost model. Pending and duplicate records are
        filtered here rather than at write time, so holding an invoice for review
        never means losing it.
        """
        return tuple(
            line
            for record in self.records(
                supplier_id=supplier_id, period=period, status=InvoiceStatus.EXTRACTED
            )
            for line in record.line_items
        )

    def cost_total(
        self,
        *,
        supplier_id: str | None = None,
        period: str | None = None,
    ) -> Decimal:
        """Summed cost of the line items the cost model may see."""
        return sum(
            (line.total_cost for line in self.line_items_for_cost_model(
                supplier_id=supplier_id, period=period
            )),
            start=Decimal("0"),
        )

    def pending(
        self,
        *,
        supplier_id: str | None = None,
        period: str | None = None,
    ) -> tuple[InvoiceRecord, ...]:
        """Invoices held for review. Not cost yet; not lost either."""
        return self.records(
            supplier_id=supplier_id, period=period, status=InvoiceStatus.PENDING_REVIEW
        )


class InMemoryInvoiceStore(InvoiceStore):
    """Process-local store. The default, and what the tests run against."""

    def __init__(self) -> None:
        self._by_fingerprint: dict[str, InvoiceRecord] = {}
        #: Invoice key -> the fingerprint that counts. Only cost-bearing records
        #: claim a key, so a pending invoice does not block its own corrected
        #: re-scan from landing later.
        self._by_invoice_key: dict[tuple[str, str], str] = {}
        self._order: list[str] = []

    def __len__(self) -> int:
        return len(self._by_fingerprint)

    def add(self, record: InvoiceRecord) -> InvoiceRecord:
        # Every check first, every mutation after: an add that raises must not
        # have touched an index.
        if record.fingerprint in self._by_fingerprint:
            raise DuplicateInvoiceError(
                f"document {record.fingerprint[:12]} already landed as invoice "
                f"{record.invoice_number!r} for supplier {record.supplier_id!r}"
            )
        if record.counts_as_cost:
            claimed = self._by_invoice_key.get(record.invoice_key)
            if claimed is not None:
                raise DuplicateInvoiceError(
                    f"invoice {record.invoice_number!r} from supplier "
                    f"{record.supplier_id!r} already counts as cost under document "
                    f"{claimed[:12]}; a second copy must not be counted twice"
                )

        self._by_fingerprint[record.fingerprint] = record
        self._order.append(record.fingerprint)
        if record.counts_as_cost:
            self._by_invoice_key[record.invoice_key] = record.fingerprint
        log.info(
            "invoice_landed",
            supplier_id=record.supplier_id,
            period=record.period,
            invoice_number=record.invoice_number,
            status=record.status.value,
            line_items=len(record.line_items),
            counts_as_cost=record.counts_as_cost,
        )
        return record

    def get(self, fingerprint: str) -> InvoiceRecord | None:
        return self._by_fingerprint.get(fingerprint)

    def find_invoice(self, supplier_id: str, invoice_number: str) -> InvoiceRecord | None:
        fingerprint = self._by_invoice_key.get((supplier_id, invoice_number))
        return None if fingerprint is None else self._by_fingerprint[fingerprint]

    def records(
        self,
        *,
        supplier_id: str | None = None,
        period: str | None = None,
        status: InvoiceStatus | None = None,
    ) -> tuple[InvoiceRecord, ...]:
        return tuple(
            record
            for record in (self._by_fingerprint[fp] for fp in self._order)
            if (supplier_id is None or record.supplier_id == supplier_id)
            and (period is None or record.period == period)
            and (status is None or record.status is status)
        )
