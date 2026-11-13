from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.requests import PaymentRequest, TransferDetails
from .models import PaymentRequestModel, PaymentSettingsModel


class SqlAlchemyPaymentRequestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, request: PaymentRequest) -> None:
        self._session.add(
            PaymentRequestModel(
                id=request.id,
                tenant_id=request.tenant_id,
                client_id=request.client_id,
                token_hash=request.token_hash,
                invoice_ids=[str(item) for item in request.invoice_ids],
                created_at=request.created_at,
                expires_at=request.expires_at,
            )
        )
        self._session.flush()

    def by_token_hash(self, token_hash: str) -> PaymentRequest | None:
        model = self._session.scalar(
            select(PaymentRequestModel).where(PaymentRequestModel.token_hash == token_hash)
        )
        if model is None:
            return None
        return PaymentRequest(
            id=model.id,
            tenant_id=model.tenant_id,
            client_id=model.client_id,
            invoice_ids=tuple(UUID(item) for item in model.invoice_ids),
            token_hash=model.token_hash,
            created_at=model.created_at,
            expires_at=model.expires_at,
        )


class SqlAlchemyPaymentSettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def transfer(self, tenant_id: UUID) -> TransferDetails | None:
        model = self._session.get(PaymentSettingsModel, tenant_id)
        if model is None:
            return None
        return TransferDetails(model.tenant_id, model.cbu_or_alias, model.holder, model.bank)

    def save_transfer(self, details: TransferDetails, now: datetime) -> None:
        model = self._session.get(PaymentSettingsModel, details.tenant_id)
        if model is None:
            model = PaymentSettingsModel(tenant_id=details.tenant_id)
            self._session.add(model)
        model.cbu_or_alias = details.cbu_or_alias
        model.holder = details.holder
        model.bank = details.bank
        model.updated_at = now
        self._session.flush()

    def remove_transfer(self, tenant_id: UUID) -> None:
        model = self._session.get(PaymentSettingsModel, tenant_id)
        if model is not None:
            self._session.delete(model)
            self._session.flush()
