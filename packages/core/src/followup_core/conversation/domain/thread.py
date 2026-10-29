from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from .errors import InvalidMessageError

MAX_MESSAGE_LENGTH = 1000


class Channel(StrEnum):
    SIMULATOR = "simulator"
    WHATSAPP = "whatsapp"


class ThreadStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class Author(StrEnum):
    VISITOR = "visitor"
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class ThreadKey:
    """Identifies one conversation. Its string form is also the LangGraph thread_id."""

    tenant_id: UUID
    channel: Channel
    visitor_id: str

    def __post_init__(self) -> None:
        if not self.visitor_id or ":" in self.visitor_id:
            raise ValueError("visitor_id must be non-empty and must not contain ':'.")

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.channel.value}:{self.visitor_id}"


@dataclass(frozen=True, slots=True)
class Thread:
    id: UUID
    key: ThreadKey
    agent_config_version: int
    status: ThreadStatus
    created_at: datetime
    last_message_at: datetime | None
    started_by_profile_id: UUID | None = None

    @property
    def tenant_id(self) -> UUID:
        return self.key.tenant_id

    @property
    def channel(self) -> Channel:
        return self.key.channel

    @property
    def visitor_id(self) -> str:
        return self.key.visitor_id


@dataclass(frozen=True, slots=True)
class Message:
    id: UUID
    thread_id: UUID
    direction: Direction
    author: Author
    text: str
    created_at: datetime
    payload: dict[str, Any] | None = None
    # Root LangSmith run of the turn that produced an outbound message, when traced.
    trace_run_id: UUID | None = None


def clean_inbound_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_MESSAGE_LENGTH:
        raise InvalidMessageError(f"A message must have 1 to {MAX_MESSAGE_LENGTH} characters.")
    return cleaned
