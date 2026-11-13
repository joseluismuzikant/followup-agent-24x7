"""The public payment page's data (`/p/<token>` on the panel, no login) and the business's
"Datos para transferencia" (Configuración). Day 9B adds the Mercado Pago checkout to the
page and the Mercado Pago account to the settings."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from followup_core.identity.domain.profile import Profile
from followup_platform.http_errors import ApiError
from pydantic import BaseModel, Field

from ..auth import current_profile, require_editor
from ..invoices.domain.status import display_status, today_in
from .application.payments import GetPaymentPage, PaymentPageNotFoundError, SaveTransferDetails
from .domain.requests import TransferDetails, TransferDetailsInvalidError
from .infrastructure.repository import SqlAlchemyPaymentSettingsRepository

ProfileDep = Annotated[Profile, Depends(current_profile)]
EditorDep = Annotated[Profile, Depends(require_editor)]
# The page is for the client who got the link: never indexed, never cached.
PRIVATE_HEADERS = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"}


class TransferRead(BaseModel):
    cbu_or_alias: str
    holder: str
    bank: str | None


class PaymentInvoiceRead(BaseModel):
    number: str
    due_date: date
    amount: str
    currency: Literal["ARS", "USD"]
    paid: bool
    status_label: str


class TotalRead(BaseModel):
    currency: Literal["ARS", "USD"]
    amount: str


class PaymentPageRead(BaseModel):
    business_name: str
    client_name: str
    invoices: list[PaymentInvoiceRead]
    # What is still owed, per currency (empty when everything is paid).
    totals: list[TotalRead]
    transfer: TransferRead | None
    # False until Day 9B: the button says "Pronto vas a poder pagar con Mercado Pago".
    mercado_pago_available: bool
    expires_at: datetime


class PaymentSettingsRead(BaseModel):
    transfer: TransferRead | None


class TransferWrite(BaseModel):
    # Both empty: remove the transfer details.
    cbu_or_alias: str = Field(default="", max_length=40)
    holder: str = Field(default="", max_length=120)
    bank: str | None = Field(default=None, max_length=80)


def _transfer(details: TransferDetails | None) -> TransferRead | None:
    if details is None:
        return None
    return TransferRead(cbu_or_alias=details.cbu_or_alias, holder=details.holder, bank=details.bank)


def build_payments_router(
    page_factory: Callable[..., GetPaymentPage],
    settings_factory: Callable[..., SqlAlchemyPaymentSettingsRepository],
    save_transfer_factory: Callable[..., SaveTransferDetails],
    timezone_factory: Callable[..., Callable[..., str]],
) -> APIRouter:
    router = APIRouter(tags=["payments"])

    @router.get("/pay/{token}", response_model=PaymentPageRead, responses={404: {}})
    def payment_page(
        token: str,
        response: Response,
        page: Annotated[GetPaymentPage, Depends(page_factory)],
        timezone_of: Annotated[Callable[..., str], Depends(timezone_factory)],
    ) -> PaymentPageRead:
        """Public: whoever has the link sees what it covers, and nothing else."""
        response.headers.update(PRIVATE_HEADERS)
        try:
            found = page.execute(token)
        except PaymentPageNotFoundError as error:
            raise ApiError(404, "payment_link_not_found") from error
        tenant_id = found.invoices[0].tenant_id
        today = today_in(timezone_of(tenant_id), datetime.now(UTC))
        return PaymentPageRead(
            business_name=found.business_name,
            client_name=found.client_name,
            invoices=[
                PaymentInvoiceRead(
                    number=invoice.display_number,
                    due_date=invoice.due_date,
                    amount=f"{invoice.amount:.2f}",
                    currency=invoice.currency.value,  # type: ignore[arg-type]
                    paid=not invoice.is_open,
                    status_label=display_status(invoice, today).label,
                )
                for invoice in found.invoices
            ],
            totals=[
                TotalRead(currency=currency, amount=f"{amount:.2f}")  # type: ignore[arg-type]
                for currency, amount in sorted(found.totals.items())
            ],
            transfer=_transfer(found.transfer),
            mercado_pago_available=found.mercado_pago_available,
            expires_at=found.expires_at,
        )

    @router.get("/payment-settings", response_model=PaymentSettingsRead)
    def get_payment_settings(
        profile: ProfileDep,
        settings: Annotated[SqlAlchemyPaymentSettingsRepository, Depends(settings_factory)],
    ) -> PaymentSettingsRead:
        return PaymentSettingsRead(transfer=_transfer(settings.transfer(profile.tenant_id)))

    @router.put("/payment-settings", response_model=PaymentSettingsRead)
    def save_payment_settings(
        payload: TransferWrite,
        profile: EditorDep,
        save: Annotated[SaveTransferDetails, Depends(save_transfer_factory)],
    ) -> PaymentSettingsRead:
        try:
            details = save.execute(
                profile.tenant_id, profile.id, payload.cbu_or_alias, payload.holder, payload.bank
            )
        except TransferDetailsInvalidError as error:
            raise ApiError(422, "transfer_details_invalid", field=error.field) from error
        return PaymentSettingsRead(transfer=_transfer(details))

    return router
