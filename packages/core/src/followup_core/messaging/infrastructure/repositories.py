from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from followup_core.conversation.infrastructure.models import MessageModel, ThreadModel

from ..domain.connection import (
    BusinessVerification,
    ConnectionStatus,
    SenderKind,
    WhatsAppConnection,
)
from ..domain.events import EventStatus, InboundEvent
from ..domain.outbound import DeliveryStatus, OutboundPart, advances
from ..domain.signup import Signup, SignupStep
from .models import (
    WebhookCounterModel,
    WhatsAppConnectionModel,
    WhatsAppInboundEventModel,
    WhatsAppOutboundModel,
    WhatsAppSignupModel,
)


def _connection(model: WhatsAppConnectionModel) -> WhatsAppConnection:
    return WhatsAppConnection(
        id=model.id,
        tenant_id=model.tenant_id,
        phone_number_id=model.phone_number_id,
        waba_id=model.waba_id,
        access_token_encrypted=model.access_token_encrypted,
        sender=SenderKind(model.sender),
        template_name=model.template_name,
        template_language=model.template_language,
        status=ConnectionStatus(model.status),
        updated_at=model.updated_at,
        display_phone_number=model.display_phone_number,
        verified_name=model.verified_name,
        last_error_code=model.last_error_code,
        last_inbound_at=model.last_inbound_at,
        connected_at=model.connected_at,
        visit_template_name=model.visit_template_name,
        visit_template_language=model.visit_template_language,
        business_id=model.business_id,
        quality_rating=model.quality_rating,
        name_status=model.name_status,
        business_verification=BusinessVerification(model.business_verification),
        failing_since=model.failing_since,
        last_health_check_at=model.last_health_check_at,
    )


class SqlAlchemyConnectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_tenant(self, tenant_id: UUID) -> WhatsAppConnection | None:
        model = self._session.scalar(
            select(WhatsAppConnectionModel).where(WhatsAppConnectionModel.tenant_id == tenant_id)
        )
        return _connection(model) if model else None

    def get_by_phone_number_id(self, phone_number_id: str) -> WhatsAppConnection | None:
        model = self._session.scalar(
            select(WhatsAppConnectionModel).where(
                WhatsAppConnectionModel.phone_number_id == phone_number_id
            )
        )
        return _connection(model) if model else None

    def save(self, connection: WhatsAppConnection) -> None:
        model = self._session.get(WhatsAppConnectionModel, connection.id)
        if model is None:
            model = WhatsAppConnectionModel(id=connection.id, tenant_id=connection.tenant_id)
            self._session.add(model)
        model.phone_number_id = connection.phone_number_id
        model.waba_id = connection.waba_id
        model.display_phone_number = connection.display_phone_number
        model.verified_name = connection.verified_name
        model.access_token_encrypted = connection.access_token_encrypted
        model.sender = connection.sender.value
        model.template_name = connection.template_name
        model.template_language = connection.template_language
        model.visit_template_name = connection.visit_template_name
        model.visit_template_language = connection.visit_template_language
        model.status = connection.status.value
        model.last_error_code = connection.last_error_code
        model.last_inbound_at = connection.last_inbound_at
        model.connected_at = connection.connected_at
        model.updated_at = connection.updated_at
        model.business_id = connection.business_id
        model.quality_rating = connection.quality_rating
        model.name_status = connection.name_status
        model.business_verification = connection.business_verification.value
        model.failing_since = connection.failing_since
        model.last_health_check_at = connection.last_health_check_at
        self._session.flush()

    def get_by_waba_id(self, waba_id: str) -> WhatsAppConnection | None:
        model = self._session.scalar(
            select(WhatsAppConnectionModel).where(WhatsAppConnectionModel.waba_id == waba_id)
        )
        return _connection(model) if model else None

    def cloud_connections(self) -> Sequence[WhatsAppConnection]:
        models = self._session.scalars(
            select(WhatsAppConnectionModel)
            .where(
                WhatsAppConnectionModel.sender == SenderKind.CLOUD.value,
                WhatsAppConnectionModel.status != ConnectionStatus.DISCONNECTED.value,
            )
            .order_by(WhatsAppConnectionModel.tenant_id)
        )
        return [_connection(model) for model in models]

    def mark_inbound(self, connection_id: UUID, at: datetime) -> None:
        self._session.execute(
            update(WhatsAppConnectionModel)
            .where(WhatsAppConnectionModel.id == connection_id)
            .values(
                last_inbound_at=func.greatest(
                    func.coalesce(WhatsAppConnectionModel.last_inbound_at, at), at
                )
            )
        )


def _event(model: WhatsAppInboundEventModel) -> InboundEvent:
    return InboundEvent(
        id=model.id,
        wamid=model.wamid,
        tenant_id=model.tenant_id,
        phone_number_id=model.phone_number_id,
        wa_id=model.wa_id,
        type=model.type,
        sent_at=model.sent_at,
        status=EventStatus(model.status),
        created_at=model.created_at,
        text=model.text,
        choice_id=model.choice_id,
    )


class SqlAlchemyInboundEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: InboundEvent, payload: Mapping[str, Any] | None) -> bool:
        statement = (
            insert(WhatsAppInboundEventModel)
            .values(
                id=event.id,
                wamid=event.wamid,
                tenant_id=event.tenant_id,
                phone_number_id=event.phone_number_id,
                wa_id=event.wa_id,
                type=event.type,
                text=event.text,
                choice_id=event.choice_id,
                sent_at=event.sent_at,
                status=event.status.value,
                payload=dict(payload) if payload is not None else None,
                created_at=event.created_at,
            )
            .on_conflict_do_nothing(index_elements=["wamid"])
            .returning(WhatsAppInboundEventModel.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    def pending_for(self, tenant_id: UUID, wa_id: str) -> Sequence[InboundEvent]:
        models = self._session.scalars(
            select(WhatsAppInboundEventModel)
            .where(
                WhatsAppInboundEventModel.tenant_id == tenant_id,
                WhatsAppInboundEventModel.wa_id == wa_id,
                WhatsAppInboundEventModel.status == EventStatus.PENDING.value,
            )
            .order_by(WhatsAppInboundEventModel.sent_at, WhatsAppInboundEventModel.created_at)
        )
        return [_event(model) for model in models]

    def get(self, event_id: UUID) -> InboundEvent | None:
        model = self._session.get(WhatsAppInboundEventModel, event_id)
        return _event(model) if model else None

    def mark(self, event_ids: Sequence[UUID], status: EventStatus) -> None:
        if event_ids:
            self._session.execute(
                update(WhatsAppInboundEventModel)
                .where(WhatsAppInboundEventModel.id.in_(list(event_ids)))
                .values(status=status.value)
            )

    def purge_payloads(self, before: datetime) -> int:
        result = self._session.execute(
            update(WhatsAppInboundEventModel)
            .where(
                WhatsAppInboundEventModel.created_at < before,
                WhatsAppInboundEventModel.payload.is_not(None),
            )
            .values(payload=None, text=None)
            .returning(WhatsAppInboundEventModel.id)
        )
        return len(result.all())


def _part(model: WhatsAppOutboundModel) -> OutboundPart:
    return OutboundPart(
        id=model.id,
        message_id=model.message_id,
        part=model.part,
        wa_id=model.wa_id,
        body=model.body,
        status=DeliveryStatus(model.status),
        wamid=model.wamid,
        error_code=model.error_code,
    )


class SqlAlchemyOutboundRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, parts: Sequence[OutboundPart]) -> None:
        for part in parts:
            self._session.add(
                WhatsAppOutboundModel(
                    id=part.id,
                    message_id=part.message_id,
                    part=part.part,
                    wa_id=part.wa_id,
                    body=dict(part.body),
                    wamid=part.wamid,
                    status=part.status.value,
                    error_code=part.error_code,
                    updated_at=func.now(),
                )
            )
        self._session.flush()

    def for_messages(self, message_ids: Sequence[UUID]) -> Sequence[OutboundPart]:
        if not message_ids:
            return []
        rows = self._session.scalars(
            select(WhatsAppOutboundModel)
            .join(MessageModel, MessageModel.id == WhatsAppOutboundModel.message_id)
            .where(WhatsAppOutboundModel.message_id.in_(list(message_ids)))
            .order_by(MessageModel.seq, WhatsAppOutboundModel.part)
        )
        return [_part(row) for row in rows]

    def mark_sent(self, part_id: UUID, wamid: str, at: datetime) -> None:
        self._session.execute(
            update(WhatsAppOutboundModel)
            .where(WhatsAppOutboundModel.id == part_id)
            .values(wamid=wamid, sent_at=at, updated_at=at)
        )

    def mark_failed(self, part_id: UUID, code: str, at: datetime) -> None:
        self._session.execute(
            update(WhatsAppOutboundModel)
            .where(WhatsAppOutboundModel.id == part_id)
            .values(status=DeliveryStatus.FAILED.value, error_code=code[:40], updated_at=at)
        )

    def mark_waiting(self, part_ids: Sequence[UUID], code: str, at: datetime) -> None:
        if part_ids:
            self._session.execute(
                update(WhatsAppOutboundModel)
                .where(WhatsAppOutboundModel.id.in_(list(part_ids)))
                .values(status=DeliveryStatus.WAITING.value, error_code=code[:40], updated_at=at)
            )

    def waiting_messages(self, tenant_id: UUID) -> Sequence[UUID]:
        rows = self._session.execute(
            select(WhatsAppOutboundModel.message_id, func.min(MessageModel.seq).label("seq"))
            .join(MessageModel, MessageModel.id == WhatsAppOutboundModel.message_id)
            .join(ThreadModel, ThreadModel.id == MessageModel.thread_id)
            .where(
                ThreadModel.tenant_id == tenant_id,
                WhatsAppOutboundModel.status == DeliveryStatus.WAITING.value,
            )
            .group_by(WhatsAppOutboundModel.message_id)
            .order_by("seq")
        )
        return [row.message_id for row in rows]

    def requeue(self, message_ids: Sequence[UUID], at: datetime) -> None:
        if message_ids:
            self._session.execute(
                update(WhatsAppOutboundModel)
                .where(
                    WhatsAppOutboundModel.message_id.in_(list(message_ids)),
                    WhatsAppOutboundModel.status == DeliveryStatus.WAITING.value,
                )
                .values(status=DeliveryStatus.QUEUED.value, error_code=None, updated_at=at)
            )

    def apply_status(
        self, wamid: str, status: DeliveryStatus, error_code: str | None, at: datetime
    ) -> bool:
        model = self._session.scalar(
            select(WhatsAppOutboundModel)
            .where(WhatsAppOutboundModel.wamid == wamid)
            .with_for_update()
        )
        if model is None:
            return False
        if advances(DeliveryStatus(model.status), status):
            model.status = status.value
            model.error_code = error_code[:40] if error_code else model.error_code
            model.updated_at = at
            self._session.flush()
        return True

    def last_inbound_at(self, message_id: UUID) -> datetime | None:
        thread_id = select(MessageModel.thread_id).where(MessageModel.id == message_id)
        return self._session.scalar(
            select(func.max(MessageModel.created_at)).where(
                MessageModel.thread_id == thread_id.scalar_subquery(),
                MessageModel.direction == "inbound",
            )
        )

    def tenant_of(self, message_id: UUID) -> UUID | None:
        return self._session.scalar(
            select(ThreadModel.tenant_id)
            .join(MessageModel, MessageModel.thread_id == ThreadModel.id)
            .where(MessageModel.id == message_id)
        )

    def statuses(self, message_ids: Sequence[UUID]) -> Mapping[UUID, Sequence[DeliveryStatus]]:
        result: dict[UUID, list[DeliveryStatus]] = {}
        if not message_ids:
            return result
        rows = self._session.execute(
            select(WhatsAppOutboundModel.message_id, WhatsAppOutboundModel.status)
            .where(WhatsAppOutboundModel.message_id.in_(list(message_ids)))
            .order_by(WhatsAppOutboundModel.part)
        )
        for message_id, status in rows:
            result.setdefault(message_id, []).append(DeliveryStatus(status))
        return result


class SqlAlchemySignupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: UUID) -> Signup | None:
        model = self._session.get(WhatsAppSignupModel, tenant_id)
        if model is None:
            return None
        return Signup(
            tenant_id=model.tenant_id,
            waba_id=model.waba_id,
            phone_number_id=model.phone_number_id,
            business_id=model.business_id,
            step=SignupStep(model.step),
            pin_encrypted=model.pin_encrypted,
            updated_at=model.updated_at,
            token_encrypted=model.token_encrypted,
            last_error_code=model.last_error_code,
        )

    def save(self, signup: Signup) -> None:
        model = self._session.get(WhatsAppSignupModel, signup.tenant_id)
        if model is None:
            model = WhatsAppSignupModel(tenant_id=signup.tenant_id)
            self._session.add(model)
        model.waba_id = signup.waba_id
        model.phone_number_id = signup.phone_number_id
        model.business_id = signup.business_id
        model.step = signup.step.value
        model.token_encrypted = signup.token_encrypted
        model.pin_encrypted = signup.pin_encrypted
        model.last_error_code = signup.last_error_code
        model.updated_at = signup.updated_at
        self._session.flush()


class SqlAlchemyWebhookCounters:
    """Hourly request counts for Salud del sistema (received, signature_rejected)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def increment(self, kind: str, at: datetime) -> None:
        hour = at.replace(minute=0, second=0, microsecond=0)
        statement = insert(WebhookCounterModel).values(hour=hour, kind=kind, count=1)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["hour", "kind"],
                set_={"count": WebhookCounterModel.count + 1},
            )
        )

    def total(self, kind: str, since: datetime) -> int:
        return int(
            self._session.scalar(
                select(func.coalesce(func.sum(WebhookCounterModel.count), 0)).where(
                    WebhookCounterModel.kind == kind,
                    WebhookCounterModel.hour >= since.replace(minute=0, second=0, microsecond=0),
                )
            )
            or 0
        )
