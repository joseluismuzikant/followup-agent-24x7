from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from followup_core.tenancy.domain.agent_config import AgentConfig
from followup_core.tenancy.domain.business_settings import ScheduleBlock

from .llm import TokenUsage, TranscriptLine
from .thread import Author, Thread, ThreadKey


@dataclass(frozen=True, slots=True)
class BusinessContext:
    tenant_id: UUID
    business_name: str
    timezone: str
    # The team's weekly schedule, for "out of hours" and for proposing visit slots.
    team_hours: tuple[ScheduleBlock, ...] = ()


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    text: str
    payload: dict[str, Any] | None = None
    # SYSTEM for events such as a hand-off: stored in the transcript, never sent to the lead.
    author: Author = Author.AGENT


@dataclass(slots=True)
class TurnMetrics:
    """Filled in while a turn runs; logged by the caller. Never holds message text."""

    model: str = ""
    prompt_versions: dict[str, str] = field(default_factory=dict)
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True, slots=True)
class AgentTurn:
    outbound: Sequence[OutboundMessage]
    state: Mapping[str, Any]
    metrics: TurnMetrics
    trace_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class TurnInput:
    agent_config: AgentConfig
    business: BusinessContext
    transcript: Sequence[TranscriptLine]
    text: str
    # When the message arrived; graphs use it instead of the wall clock, so tests can pin it.
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    # A choice the visitor tapped (a reply button): it wins over the model's reading.
    choice_id: str | None = None
    # How to reach the visitor when the channel already knows it (WhatsApp: their number).
    visitor_contact: str | None = None


class AgentRuntime(Protocol):
    """Runs one agent turn. It knows nothing about channels."""

    def handle(self, thread: Thread, turn: TurnInput) -> AgentTurn: ...

    def state(self, key: ThreadKey) -> Mapping[str, Any]:
        """The latest graph state of the thread; empty before its first turn."""
        ...
