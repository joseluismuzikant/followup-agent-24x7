from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from .invoice import Invoice
from .number import InvoiceType


class Tab(StrEnum):
    """C2's tabs. "Pendientes" is every owed invoice (open or promised); "Vencidas" the owed
    ones past due; "Con promesa" the ones whose promise has not passed; "Pagadas este mes"
    uses the tenant's month."""

    PENDING = "pending"
    OVERDUE = "overdue"
    PROMISED = "promised"
    PAID_THIS_MONTH = "paid_this_month"


@dataclass(frozen=True, slots=True)
class InvoiceRow:
    invoice: Invoice
    client_name: str
    client_subtitle: str | None


@dataclass(frozen=True, slots=True)
class InvoiceQuery:
    tab: Tab
    q: str
    # In the tenant's timezone.
    today: date
    month_start: date
    next_month_start: date
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class InvoiceListing:
    rows: Sequence[InvoiceRow]
    total: int
    counts: dict[Tab, int]


@dataclass(frozen=True, slots=True)
class Amounts:
    amount: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class Summary:
    to_collect: Amounts
    overdue: Amounts
    to_collect_usd: Amounts
    overdue_usd: Amounts


class InvoiceRepository(Protocol):
    def get(self, tenant_id: UUID, invoice_id: UUID) -> Invoice | None: ...

    def find_by_number(
        self, tenant_id: UUID, invoice_type: InvoiceType, point_of_sale: int, number: int
    ) -> Invoice | None: ...

    def add(self, invoice: Invoice) -> None: ...

    def save(self, invoice: Invoice) -> None: ...

    def listing(self, tenant_id: UUID, query: InvoiceQuery) -> InvoiceListing: ...

    def for_client(self, tenant_id: UUID, client_id: UUID) -> Sequence[Invoice]: ...

    def summary(self, tenant_id: UUID, today: date) -> Summary: ...

    def has_any(self, tenant_id: UUID) -> bool: ...
