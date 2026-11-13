"""The public payment page behind a reminder's link, and the business's transfer details.

The page shows only what the link covers: the business's name, the client's name and the
covered invoices with number, due date and amount (never a CUIT, an email or another
client's data). An unknown, malformed and expired token are the same "not found"."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ...invoices.domain.invoice import Invoice
from ...reminders.domain.repositories import OwedInvoices
from ..domain.requests import TransferDetails, looks_like_token, token_hash, validate_transfer
from ..infrastructure.repository import (
    SqlAlchemyPaymentRequestRepository,
    SqlAlchemyPaymentSettingsRepository,
)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class PaymentPageNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class PaymentPage:
    business_name: str
    client_name: str
    invoices: Sequence[Invoice]
    # Per currency, of the invoices still owed.
    totals: dict[str, Decimal]
    transfer: TransferDetails | None
    expires_at: datetime
    # Day 9B: the Mercado Pago checkout.
    mercado_pago_available: bool = False


class GetPaymentPage:
    def __init__(
        self,
        requests: SqlAlchemyPaymentRequestRepository,
        settings: SqlAlchemyPaymentSettingsRepository,
        owed: OwedInvoices,
        business_name: Callable[[UUID], str],
        is_active: Callable[[UUID], bool],
        clock: Clock = utc_now,
    ) -> None:
        self._requests = requests
        self._settings = settings
        self._owed = owed
        self._business_name = business_name
        self._is_active = is_active
        self._clock = clock

    def execute(self, token: str) -> PaymentPage:
        if not looks_like_token(token):
            raise PaymentPageNotFoundError()
        request = self._requests.by_token_hash(token_hash(token))
        if (
            request is None
            or request.expired(self._clock())
            or not self._is_active(request.tenant_id)
        ):
            raise PaymentPageNotFoundError()
        invoices = [
            invoice
            for invoice in self._owed.invoices(request.tenant_id, list(request.invoice_ids))
            if invoice.client_id == request.client_id
        ]
        clients = self._owed.clients(request.tenant_id, [request.client_id])
        client = clients.get(request.client_id)
        if client is None or not invoices:
            raise PaymentPageNotFoundError()
        totals: dict[str, Decimal] = {}
        for invoice in invoices:
            if invoice.is_open:
                key = invoice.currency.value
                totals[key] = totals.get(key, Decimal(0)) + invoice.amount
        return PaymentPage(
            business_name=self._business_name(request.tenant_id),
            client_name=client.name,
            invoices=invoices,
            totals=totals,
            transfer=self._settings.transfer(request.tenant_id),
            expires_at=request.expires_at,
        )


class SaveTransferDetails:
    def __init__(
        self,
        settings: SqlAlchemyPaymentSettingsRepository,
        audit: AuditLog,
        clock: Clock = utc_now,
    ) -> None:
        self._settings = settings
        self._audit = audit
        self._clock = clock

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        cbu_or_alias: str,
        holder: str,
        bank: str | None,
    ) -> TransferDetails | None:
        """Empty CBU/alias and holder remove them."""
        now = self._clock()
        details: TransferDetails | None
        if not cbu_or_alias.strip() and not holder.strip():
            self._settings.remove_transfer(tenant_id)
            details = None
        else:
            details = validate_transfer(tenant_id, cbu_or_alias, holder, bank)
            self._settings.save_transfer(details, now)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER,
                CuentasAction.TRANSFER_DETAILS_SAVED,
                {"removed": "true" if details is None else "false"},
                actor_profile_id=profile_id,
            )
        )
        return details
