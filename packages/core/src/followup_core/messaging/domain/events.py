from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class EventStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    IGNORED = "ignored"  # no connected tenant for its phone_number_id


@dataclass(frozen=True, slots=True)
class InboundEvent:
    id: UUID
    wamid: str
    tenant_id: UUID | None
    phone_number_id: str
    wa_id: str
    type: str
    sent_at: datetime
    status: EventStatus
    created_at: datetime
    text: str | None = None
    choice_id: str | None = None

    @property
    def is_text(self) -> bool:
        return self.type in ("text", "button")
