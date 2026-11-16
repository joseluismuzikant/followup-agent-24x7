"""An invoice the business issued to one of its clients, and what happened to it.

The lifecycle is stored (`InvoiceStatus`); what the panel shows ("Vencida · 12 días", "Por
vencer") is derived from it and today's date in status.py. An invoice is owed while it is
open or promised (the client promised to pay by a date; reminders pause until then). Day 10
adds a payment under review, as a new member of the same enum.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID, uuid4

from .errors import InvoiceAlreadyPaidError, InvoiceInvalidError
from .number import MAX_NUMBER, MAX_POINT_OF_SALE, InvoiceType, format_number

MAX_AMOUNT = Decimal("9999999999.99")
MAX_DESCRIPTION = 500
MAX_REASON = 500
MAX_REFERENCE = 120
# A promise further away than this is not a promise.
MAX_PROMISE_DAYS = 90


class InvoiceStatus(StrEnum):
    OPEN = "open"
    PROMISED = "promised"
    PAID = "paid"
    CANCELLED = "cancelled"


# Still owed: what Inicio, the tabs and the reminders count.
OWED_STATUSES = (InvoiceStatus.OPEN, InvoiceStatus.PROMISED)


class Currency(StrEnum):
    ARS = "ARS"
    USD = "USD"


class PaidVia(StrEnum):
    MANUAL = "manual"
    TRANSFER = "transfer"
    MERCADO_PAGO = "mercado_pago"
    OTHER = "other"


PAID_VIA_LABELS = {
    PaidVia.MANUAL: "Manual",
    PaidVia.TRANSFER: "Transferencia",
    PaidVia.MERCADO_PAGO: "Mercado Pago",
    PaidVia.OTHER: "Otro",
}


def parse_amount(value: Decimal | str) -> Decimal:
    """Two decimals, more than zero. Never a float."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError) as error:
        raise InvoiceInvalidError("amount") from error
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        raise InvoiceInvalidError("amount")
    if amount != amount.quantize(Decimal("0.01")):
        raise InvoiceInvalidError("amount")
    return amount.quantize(Decimal("0.01"))


@dataclass(frozen=True, slots=True)
class InvoiceFields:
    client_id: UUID
    invoice_type: InvoiceType
    point_of_sale: int
    number: int
    issue_date: date
    due_date: date
    amount: Decimal
    currency: Currency = Currency.ARS
    description: str = ""


def _validated(fields: InvoiceFields) -> InvoiceFields:
    if not 1 <= fields.point_of_sale <= MAX_POINT_OF_SALE:
        raise InvoiceInvalidError("point_of_sale")
    if not 1 <= fields.number <= MAX_NUMBER:
        raise InvoiceInvalidError("number")
    if fields.due_date < fields.issue_date:
        raise InvoiceInvalidError("due_date")
    description = " ".join(fields.description.split())
    if len(description) > MAX_DESCRIPTION:
        raise InvoiceInvalidError("description")
    return replace(fields, amount=parse_amount(fields.amount), description=description)


@dataclass(frozen=True, slots=True)
class Invoice:
    id: UUID
    tenant_id: UUID
    client_id: UUID
    invoice_type: InvoiceType
    point_of_sale: int
    number: int
    issue_date: date
    due_date: date
    amount: Decimal
    currency: Currency
    description: str
    status: InvoiceStatus
    created_at: datetime
    updated_at: datetime
    paid_at: date | None = None
    paid_via: PaidVia | None = None
    payment_reference: str | None = None
    cancelled_reason: str | None = None
    # The day the client promised to pay by (status PROMISED).
    promised_until: date | None = None

    @classmethod
    def create(cls, tenant_id: UUID, fields: InvoiceFields, now: datetime) -> "Invoice":
        valid = _validated(fields)
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            client_id=valid.client_id,
            invoice_type=valid.invoice_type,
            point_of_sale=valid.point_of_sale,
            number=valid.number,
            issue_date=valid.issue_date,
            due_date=valid.due_date,
            amount=valid.amount,
            currency=valid.currency,
            description=valid.description,
            status=InvoiceStatus.OPEN,
            created_at=now,
            updated_at=now,
        )

    @property
    def display_number(self) -> str:
        return format_number(self.invoice_type, self.point_of_sale, self.number)

    @property
    def is_open(self) -> bool:
        """Still owed (open or promised)."""
        return self.status in OWED_STATUSES

    def _require_owed(self) -> None:
        if self.status is InvoiceStatus.PAID:
            raise InvoiceAlreadyPaidError(str(self.id))
        if self.status not in OWED_STATUSES:
            raise InvoiceInvalidError("status")

    def promise(self, until: date, today: date, now: datetime) -> "Invoice":
        """ "Registrar promesa de pago": reminders pause until that day (included)."""
        self._require_owed()
        if not today <= until <= today + timedelta(days=MAX_PROMISE_DAYS):
            raise InvoiceInvalidError("promised_until")
        return replace(self, status=InvoiceStatus.PROMISED, promised_until=until, updated_at=now)

    def remove_promise(self, now: datetime) -> "Invoice":
        """ "Quitar promesa" (or the promise's day passed): back to open."""
        if self.status is not InvoiceStatus.PROMISED:
            raise InvoiceInvalidError("status")
        return replace(self, status=InvoiceStatus.OPEN, promised_until=None, updated_at=now)

    def promise_expired(self, today: date) -> bool:
        return (
            self.status is InvoiceStatus.PROMISED
            and self.promised_until is not None
            and self.promised_until < today
        )

    def with_changes(self, fields: InvoiceFields, now: datetime) -> "Invoice":
        """Editing an invoice that is no longer owed would rewrite what was collected."""
        self._require_owed()
        valid = _validated(fields)
        return replace(
            self,
            client_id=valid.client_id,
            invoice_type=valid.invoice_type,
            point_of_sale=valid.point_of_sale,
            number=valid.number,
            issue_date=valid.issue_date,
            due_date=valid.due_date,
            amount=valid.amount,
            currency=valid.currency,
            description=valid.description,
            updated_at=now,
        )

    def mark_paid(
        self, paid_at: date, paid_via: PaidVia, reference: str | None, now: datetime
    ) -> "Invoice":
        self._require_owed()
        if paid_at > now.date():
            raise InvoiceInvalidError("paid_at")
        reference = " ".join((reference or "").split()) or None
        if reference is not None and len(reference) > MAX_REFERENCE:
            raise InvoiceInvalidError("reference")
        return replace(
            self,
            status=InvoiceStatus.PAID,
            paid_at=paid_at,
            paid_via=paid_via,
            payment_reference=reference,
            promised_until=None,
            updated_at=now,
        )

    def cancel(self, reason: str, now: datetime) -> "Invoice":
        """ "Anular": the invoice stops counting as owed. Only an owed one."""
        self._require_owed()
        text = " ".join(reason.split())
        if not text or len(text) > MAX_REASON:
            raise InvoiceInvalidError("reason")
        return replace(
            self,
            status=InvoiceStatus.CANCELLED,
            cancelled_reason=text,
            promised_until=None,
            updated_at=now,
        )
