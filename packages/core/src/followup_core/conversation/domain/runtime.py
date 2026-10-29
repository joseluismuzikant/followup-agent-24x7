from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from followup_core.tenancy.domain.agent_config import AgentConfig

from .llm import TokenUsage, TranscriptLine
from .thread import Thread, ThreadKey


@dataclass(frozen=True, slots=True)
class BusinessContext:
    tenant_id: UUID
    business_name: str
    timezone: str


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    text: str
    payload: dict[str, Any] | None = None


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


class AgentRuntime(Protocol):
    """Runs one agent turn. It knows nothing about channels."""

    def handle(self, thread: Thread, turn: TurnInput) -> AgentTurn: ...

    def state(self, key: ThreadKey) -> Mapping[str, Any]:
        """The latest graph state of the thread; empty before its first turn."""
        ...
