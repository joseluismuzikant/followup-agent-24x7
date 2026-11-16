"""Facturas: list with tabs and search, detail, manual create and edit, mark as paid and
cancel. "Today" and "this month" are the business's (its timezone), not the server's."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ...clients.domain.client import Client
from ...clients.domain.errors import ClientNotFoundError
from ...clients.domain.repository import ClientRepository
from ..domain.errors import InvoiceNotFoundError, InvoiceNumberTakenError
from ..domain.invoice import Invoice, InvoiceFields, PaidVia
from ..domain.repository import InvoiceListing, InvoiceQuery, InvoiceRepository, Summary, Tab
from ..domain.status import today_in

Clock = Callable[[], datetime]
TimezoneOf = Callable[[UUID], str]
PAGE_SIZE = 25


def utc_now() -> datetime:
    return datetime.now(UTC)


def month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    following = (
        date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    )
    return start, following


@dataclass(frozen=True, slots=True)
class InvoiceView:
    invoice: Invoice
    client: Client
    today: date


class ListInvoices:
    def __init__(
        self, invoices: InvoiceRepository, timezone_of: TimezoneOf, clock: Clock = utc_now
    ) -> None:
        self._invoices = invoices
        self._timezone_of = timezone_of
        self._clock = clock

    def today(self, tenant_id: UUID) -> date:
        return today_in(self._timezone_of(tenant_id), self._clock())

    def execute(self, tenant_id: UUID, tab: Tab, q: str = "", page: int = 1) -> InvoiceListing:
        today = self.today(tenant_id)
        month_start, next_month = month_bounds(today)
        return self._invoices.listing(
            tenant_id,
            InvoiceQuery(tab, q, today, month_start, next_month, max(page, 1), PAGE_SIZE),
        )


class GetSummary:
    """Inicio's two cards: total to collect and overdue (more of C1 on Day 11)."""

    def __init__(
        self, invoices: InvoiceRepository, timezone_of: TimezoneOf, clock: Clock = utc_now
    ) -> None:
        self._invoices = invoices
        self._timezone_of = timezone_of
        self._clock = clock

    def execute(self, tenant_id: UUID) -> Summary:
        return self._invoices.summary(
            tenant_id, today_in(self._timezone_of(tenant_id), self._clock())
        )


class _InvoiceUseCase:
    def __init__(
        self,
        invoices: InvoiceRepository,
        clients: ClientRepository,
        audit: AuditLog,
        timezone_of: TimezoneOf,
        clock: Clock = utc_now,
    ) -> None:
        self._invoices = invoices
        self._clients = clients
        self._audit = audit
        self._timezone_of = timezone_of
        self._clock = clock

    def _view(self, invoice: Invoice) -> InvoiceView:
        client = self._clients.get(invoice.tenant_id, invoice.client_id)
        assert client is not None  # a foreign key
        return InvoiceView(
            invoice, client, today_in(self._timezone_of(invoice.tenant_id), self._clock())
        )

    def _require(self, tenant_id: UUID, invoice_id: UUID) -> Invoice:
        invoice = self._invoices.get(tenant_id, invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(str(invoice_id))
        return invoice

    def _require_client(self, tenant_id: UUID, client_id: UUID) -> None:
        if self._clients.get(tenant_id, client_id) is None:
            raise ClientNotFoundError(str(client_id))

    def _number_free(self, tenant_id: UUID, invoice: Invoice) -> None:
        other = self._invoices.find_by_number(
            tenant_id, invoice.invoice_type, invoice.point_of_sale, invoice.number
        )
        if other is not None and other.id != invoice.id:
            raise InvoiceNumberTakenError(invoice.display_number)

    def _record(
        self, invoice: Invoice, profile_id: UUID, action: CuentasAction, **details: str
    ) -> None:
        self._audit.record(
            AuditEvent(
                invoice.tenant_id,
                self._clock(),
                ActorKind.USER,
                action,
                {"invoice_id": str(invoice.id), **details},
                actor_profile_id=profile_id,
            )
        )


class GetInvoice(_InvoiceUseCase):
    def execute(self, tenant_id: UUID, invoice_id: UUID) -> InvoiceView:
        return self._view(self._require(tenant_id, invoice_id))


class CreateInvoice(_InvoiceUseCase):
    def execute(self, tenant_id: UUID, profile_id: UUID, fields: InvoiceFields) -> InvoiceView:
        self._require_client(tenant_id, fields.client_id)
        invoice = Invoice.create(tenant_id, fields, self._clock())
        self._number_free(tenant_id, invoice)
        self._invoices.add(invoice)
        self._record(invoice, profile_id, CuentasAction.INVOICE_CREATED)
        return self._view(invoice)


class UpdateInvoice(_InvoiceUseCase):
    def execute(
        self, tenant_id: UUID, profile_id: UUID, invoice_id: UUID, fields: InvoiceFields
    ) -> InvoiceView:
        self._require_client(tenant_id, fields.client_id)
        invoice = self._require(tenant_id, invoice_id).with_changes(fields, self._clock())
        self._number_free(tenant_id, invoice)
        self._invoices.save(invoice)
        self._record(invoice, profile_id, CuentasAction.INVOICE_UPDATED)
        return self._view(invoice)


class MarkInvoicePaid(_InvoiceUseCase):
    """ "Marcar como pagada": the date, how it was paid and an optional reference."""

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        invoice_id: UUID,
        paid_at: date,
        paid_via: PaidVia,
        reference: str | None = None,
    ) -> InvoiceView:
        invoice = self._require(tenant_id, invoice_id).mark_paid(
            paid_at, paid_via, reference, self._clock()
        )
        self._invoices.save(invoice)
        self._record(invoice, profile_id, CuentasAction.INVOICE_PAID, paid_via=paid_via.value)
        return self._view(invoice)


class CancelInvoice(_InvoiceUseCase):
    """ "Anular", with a reason (kept on the invoice, not in the audit log)."""

    def execute(
        self, tenant_id: UUID, profile_id: UUID, invoice_id: UUID, reason: str
    ) -> InvoiceView:
        invoice = self._require(tenant_id, invoice_id).cancel(reason, self._clock())
        self._invoices.save(invoice)
        self._record(invoice, profile_id, CuentasAction.INVOICE_CANCELLED)
        return self._view(invoice)


class PromiseInvoice(_InvoiceUseCase):
    """ "Registrar promesa de pago": reminders pause until that day (Day 10's agent creates
    promises from the client's replies; today the owner does)."""

    def execute(
        self, tenant_id: UUID, profile_id: UUID, invoice_id: UUID, until: date
    ) -> InvoiceView:
        now = self._clock()
        today = today_in(self._timezone_of(tenant_id), now)
        invoice = self._require(tenant_id, invoice_id).promise(until, today, now)
        self._invoices.save(invoice)
        self._record(
            invoice, profile_id, CuentasAction.PROMISE_REGISTERED, promised_until=until.isoformat()
        )
        return self._view(invoice)


class RemovePromise(_InvoiceUseCase):
    """ "Quitar promesa": the sequence goes on from the next pending step."""

    def execute(self, tenant_id: UUID, profile_id: UUID, invoice_id: UUID) -> InvoiceView:
        invoice = self._require(tenant_id, invoice_id).remove_promise(self._clock())
        self._invoices.save(invoice)
        self._record(invoice, profile_id, CuentasAction.PROMISE_REMOVED)
        return self._view(invoice)
