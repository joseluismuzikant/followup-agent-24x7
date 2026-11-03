from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from followup_core.conversation.infrastructure.models import MessageModel, ThreadModel

from ..domain.connection import ConnectionStatus, SenderKind, WhatsAppConnection
from ..domain.events import EventStatus, InboundEvent
from ..domain.outbound import DeliveryStatus, OutboundPart, advances
from .models import WhatsAppConnectionModel, WhatsAppInboundEventModel, WhatsAppOutboundModel


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
        model.status = connection.status.value
        model.last_error_code = connection.last_error_code
        model.last_inbound_at = connection.last_inbound_at
        model.connected_at = connection.connected_at
        model.updated_at = connection.updated_at
        self._session.flush()

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
            .values(wamid=wamid, updated_at=at)
        )

    def mark_failed(self, part_id: UUID, code: str, at: datetime) -> None:
        self._session.execute(
            update(WhatsAppOutboundModel)
            .where(WhatsAppOutboundModel.id == part_id)
            .values(status=DeliveryStatus.FAILED.value, error_code=code[:40], updated_at=at)
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
