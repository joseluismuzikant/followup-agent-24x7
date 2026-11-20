from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .domain import (
    DELIVERY_LOG_SIZE,
    DeliveryStatus,
    Integration,
    LeadDelivery,
    Provider,
    SyncFailure,
    SyncReport,
    SyncStatus,
)
from .models import IntegrationModel, LeadDeliveryModel, SyncReportModel


def _integration(model: IntegrationModel) -> Integration:
    return Integration(
        tenant_id=model.tenant_id,
        provider=Provider(model.provider),
        enabled=model.enabled,
        options=dict(model.options or {}),
        updated_at=model.updated_at,
        credentials=model.credentials,
        public_id=model.public_id,
        last_sync_at=model.last_sync_at,
        last_sync_status=SyncStatus(model.last_sync_status) if model.last_sync_status else None,
        last_delivery_at=model.last_delivery_at,
        last_delivery_status=DeliveryStatus(model.last_delivery_status)
        if model.last_delivery_status
        else None,
        last_error_code=model.last_error_code,
    )


class SqlAlchemyIntegrationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: UUID, provider: Provider) -> Integration | None:
        model = self._session.get(IntegrationModel, (tenant_id, provider.value))
        return _integration(model) if model is not None else None

    def save(self, item: Integration) -> None:
        model = self._session.get(IntegrationModel, (item.tenant_id, item.provider.value))
        if model is None:
            model = IntegrationModel(tenant_id=item.tenant_id, provider=item.provider.value)
            self._session.add(model)
        model.enabled = item.enabled
        model.options = dict(item.options)
        model.credentials = item.credentials
        model.public_id = item.public_id
        model.last_sync_at = item.last_sync_at
        model.last_sync_status = item.last_sync_status.value if item.last_sync_status else None
        model.last_delivery_at = item.last_delivery_at
        model.last_delivery_status = (
            item.last_delivery_status.value if item.last_delivery_status else None
        )
        model.last_error_code = item.last_error_code
        model.updated_at = item.updated_at
        self._session.flush()

    def enabled(self, provider: Provider) -> Sequence[Integration]:
        models = self._session.scalars(
            select(IntegrationModel).where(
                IntegrationModel.provider == provider.value, IntegrationModel.enabled
            )
        )
        return [_integration(model) for model in models]

    def by_public_id(self, public_id: str) -> Integration | None:
        model = self._session.scalar(
            select(IntegrationModel).where(
                IntegrationModel.public_id == public_id,
                IntegrationModel.provider == Provider.WIDGET.value,
            )
        )
        return _integration(model) if model is not None else None


class SqlAlchemySyncReportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, report: SyncReport) -> None:
        self._session.add(
            SyncReportModel(
                id=report.id,
                tenant_id=report.tenant_id,
                provider=report.provider.value,
                started_at=report.started_at,
                finished_at=report.finished_at,
                created=report.created,
                updated=report.updated,
                paused=report.paused,
                unchanged=report.unchanged,
                failed=[
                    {"external_id": f.external_id, "title": f.title, "reason": f.reason}
                    for f in report.failed
                ],
                error_code=report.error_code,
            )
        )
        self._session.flush()

    def last(self, tenant_id: UUID, provider: Provider) -> SyncReport | None:
        model = self._session.scalar(
            select(SyncReportModel)
            .where(
                SyncReportModel.tenant_id == tenant_id,
                SyncReportModel.provider == provider.value,
            )
            .order_by(SyncReportModel.started_at.desc())
            .limit(1)
        )
        if model is None:
            return None
        return SyncReport(
            id=model.id,
            tenant_id=model.tenant_id,
            provider=Provider(model.provider),
            started_at=model.started_at,
            finished_at=model.finished_at,
            created=model.created,
            updated=model.updated,
            paused=model.paused,
            unchanged=model.unchanged,
            failed=tuple(
                SyncFailure(item["external_id"], item["title"], item["reason"])
                for item in model.failed
            ),
            error_code=model.error_code,
        )


def _delivery(model: LeadDeliveryModel) -> LeadDelivery:
    return LeadDelivery(
        id=model.id,
        tenant_id=model.tenant_id,
        provider=Provider(model.provider),
        event=model.event,
        status=DeliveryStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        lead_id=model.lead_id,
        attempts=model.attempts,
        status_code=model.status_code,
        error_code=model.error_code,
        delivered_at=model.delivered_at,
    )


def _copy_delivery(delivery: LeadDelivery, model: LeadDeliveryModel) -> None:
    model.tenant_id = delivery.tenant_id
    model.lead_id = delivery.lead_id
    model.provider = delivery.provider.value
    model.event = delivery.event
    model.status = delivery.status.value
    model.attempts = delivery.attempts
    model.status_code = delivery.status_code
    model.error_code = delivery.error_code
    model.created_at = delivery.created_at
    model.updated_at = delivery.updated_at
    model.delivered_at = delivery.delivered_at


class SqlAlchemyDeliveryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, delivery: LeadDelivery) -> None:
        model = LeadDeliveryModel(id=delivery.id)
        _copy_delivery(delivery, model)
        self._session.add(model)
        self._session.flush()

    def get(self, delivery_id: UUID) -> LeadDelivery | None:
        model = self._session.get(LeadDeliveryModel, delivery_id)
        return _delivery(model) if model is not None else None

    def save(self, delivery: LeadDelivery) -> None:
        model = self._session.get(LeadDeliveryModel, delivery.id)
        if model is None:
            return
        _copy_delivery(delivery, model)
        self._session.flush()

    def recent(
        self, tenant_id: UUID, provider: Provider, limit: int = DELIVERY_LOG_SIZE
    ) -> Sequence[LeadDelivery]:
        models = self._session.scalars(
            select(LeadDeliveryModel)
            .where(
                LeadDeliveryModel.tenant_id == tenant_id,
                LeadDeliveryModel.provider == provider.value,
            )
            .order_by(LeadDeliveryModel.created_at.desc(), LeadDeliveryModel.id)
            .limit(limit)
        )
        return [_delivery(model) for model in models]

    def for_lead(self, tenant_id: UUID, lead_id: UUID) -> Sequence[LeadDelivery]:
        models = self._session.scalars(
            select(LeadDeliveryModel)
            .where(LeadDeliveryModel.tenant_id == tenant_id, LeadDeliveryModel.lead_id == lead_id)
            .order_by(LeadDeliveryModel.created_at)
        )
        return [_delivery(model) for model in models]
