from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from .connection import WhatsAppConnection
from .events import EventStatus, InboundEvent
from .outbound import DeliveryStatus, OutboundPart


class ConnectionRepository(Protocol):
    def get_by_tenant(self, tenant_id: UUID) -> WhatsAppConnection | None: ...

    def get_by_phone_number_id(self, phone_number_id: str) -> WhatsAppConnection | None: ...

    def save(self, connection: WhatsAppConnection) -> None: ...

    def mark_inbound(self, connection_id: UUID, at: datetime) -> None: ...

    def get_by_waba_id(self, waba_id: str) -> WhatsAppConnection | None: ...

    def cloud_connections(self) -> Sequence[WhatsAppConnection]:
        """Connections that talk to Meta (the health check reads them)."""
        ...


class InboundEventRepository(Protocol):
    def add(self, event: InboundEvent, payload: Mapping[str, Any] | None) -> bool:
        """False when the wamid is already stored (Meta retries): the database drops it."""
        ...

    def pending_for(self, tenant_id: UUID, wa_id: str) -> Sequence[InboundEvent]:
        """Pending events of one conversation, oldest first."""
        ...

    def get(self, event_id: UUID) -> InboundEvent | None: ...

    def mark(self, event_ids: Sequence[UUID], status: EventStatus) -> None: ...

    def purge_payloads(self, before: datetime) -> int: ...


class OutboundRepository(Protocol):
    def add(self, parts: Sequence[OutboundPart]) -> None: ...

    def for_messages(self, message_ids: Sequence[UUID]) -> Sequence[OutboundPart]:
        """The parts of these messages in sending order."""
        ...

    def mark_sent(self, part_id: UUID, wamid: str, at: datetime) -> None: ...

    def mark_failed(self, part_id: UUID, code: str, at: datetime) -> None: ...

    def mark_waiting(self, part_ids: Sequence[UUID], code: str, at: datetime) -> None: ...

    def waiting_messages(self, tenant_id: UUID) -> Sequence[UUID]:
        """Messages with parts waiting for the connection, in conversation order."""
        ...

    def requeue(self, message_ids: Sequence[UUID], at: datetime) -> None: ...

    def apply_status(
        self, wamid: str, status: DeliveryStatus, error_code: str | None, at: datetime
    ) -> bool:
        """Moves a part forward (never back). False when the wamid is unknown."""
        ...

    def last_inbound_at(self, message_id: UUID) -> datetime | None:
        """When the visitor last wrote in the thread of this message (the 24 h window)."""
        ...

    def tenant_of(self, message_id: UUID) -> UUID | None: ...

    def statuses(self, message_ids: Sequence[UUID]) -> Mapping[UUID, Sequence[DeliveryStatus]]: ...
