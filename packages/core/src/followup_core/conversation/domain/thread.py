from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from .errors import InvalidMessageError

MAX_MESSAGE_LENGTH = 1000


class Channel(StrEnum):
    SIMULATOR = "simulator"
    WHATSAPP = "whatsapp"


class ThreadStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Control(StrEnum):
    """Who answers the visitor: the agent, or a person from the team (takeover)."""

    AGENT = "agent"
    HUMAN = "human"


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
    control: Control = Control.AGENT
    controlled_by_profile_id: UUID | None = None
    control_changed_at: datetime | None = None

    @property
    def is_taken_over(self) -> bool:
        return self.control is Control.HUMAN

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
    # "text", or what a channel delivered that the agent cannot read ("audio", "image", ...).
    content_type: str = "text"
    # Who on the team wrote a `human` message.
    author_profile_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InboundPart:
    """One message the visitor sent. A channel may deliver several before the agent answers
    (a burst on WhatsApp); each is stored on its own and the agent reads them together."""

    text: str
    received_at: datetime | None = None
    content_type: str = "text"


def clean_inbound_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned or len(cleaned) > MAX_MESSAGE_LENGTH:
        raise InvalidMessageError(f"A message must have 1 to {MAX_MESSAGE_LENGTH} characters.")
    return cleaned


def system_event(thread: Thread, text: str, at: datetime) -> Message:
    """An event shown centered in the transcript ("Ana tomó la conversación"). Never sent
    to the visitor."""
    return Message(uuid4(), thread.id, Direction.OUTBOUND, Author.SYSTEM, text, at)


def take_over(thread: Thread, profile_id: UUID, name: str, at: datetime) -> tuple[Thread, Message]:
    """A person takes the conversation; the agent stops answering. Taking it from another
    person moves control to this one."""
    taken = replace(
        thread, control=Control.HUMAN, controlled_by_profile_id=profile_id, control_changed_at=at
    )
    return taken, system_event(thread, f"{name} tomó la conversación", at)


def release(thread: Thread, name: str, at: datetime) -> tuple[Thread, Message | None]:
    """Gives the conversation back to the agent. A no-op when the agent already has it."""
    if not thread.is_taken_over:
        return thread, None
    released = replace(
        thread, control=Control.AGENT, controlled_by_profile_id=None, control_changed_at=at
    )
    return released, system_event(thread, f"{name} devolvió la conversación al agente", at)
