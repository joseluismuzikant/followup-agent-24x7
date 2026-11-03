"""Runs the inmo24x7 lead graph through the real LangGraph runtime, with the fake LLM, an
in-memory checkpointer and a pinned clock, so whole conversations are deterministic."""

from collections.abc import Sequence
from datetime import UTC, datetime, time
from typing import Any
from uuid import UUID, uuid4

from followup_core.conversation.domain.llm import ReplyRequest
from followup_core.conversation.domain.runtime import BusinessContext, TurnInput
from followup_core.conversation.domain.thread import Channel, Thread, ThreadKey, ThreadStatus
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.langgraph_runtime import (
    LangGraphRuntime,
    TurnTracing,
)
from followup_core.tenancy.domain.agent_config import AgentConfig
from followup_core.tenancy.domain.business_settings import ScheduleBlock
from inmo24x7_api.defaults import build_setup_defaults
from inmo24x7_api.leads.graph import build_lead_graph
from inmo24x7_api.leads.tools import lead_handlers, lead_tools
from inmo24x7_api.properties.domain.search import Listing, PropertyMatch, PropertyQuery, rank
from inmo24x7_api.properties.infrastructure.sample import SAMPLE_LISTINGS
from langgraph.checkpoint.memory import InMemorySaver

DEFAULTS = build_setup_defaults().agent_config
WEEKDAYS_9_18 = tuple(ScheduleBlock(day, time(9), time(18)) for day in range(5))
TIMEZONE = "America/Argentina/Buenos_Aires"
# Tuesday 3 November 2026, 11:00 in Buenos Aires (inside team hours).
TUESDAY_11 = datetime(2026, 11, 3, 14, 0, tzinfo=UTC)


class ListingSearch:
    """Any fixed set of listings (the sample fixture by default)."""

    def __init__(self, listings: Sequence[Listing] = SAMPLE_LISTINGS) -> None:
        self.listings = listings

    def search(self, tenant_id: UUID, query: PropertyQuery) -> Sequence[PropertyMatch]:
        return rank(self.listings, query)


class RecordingLlm(FakeLanguageModel):
    def __init__(self) -> None:
        super().__init__()
        self.replies: list[ReplyRequest] = []

    def compose_reply(self, request: ReplyRequest):
        self.replies.append(request)
        return super().compose_reply(request)


class Chat:
    def __init__(
        self,
        config: AgentConfig = DEFAULTS,
        *,
        search: ListingSearch | None = None,
        team_hours: tuple[ScheduleBlock, ...] = WEEKDAYS_9_18,
        now: datetime = TUESDAY_11,
        tracing: TurnTracing | None = None,
        visitor_contact: str | None = None,
    ) -> None:
        self.visitor_contact = visitor_contact
        self.config = config
        self.llm = RecordingLlm()
        self.tool_calls: list[str] = []
        self.runtime = LangGraphRuntime(
            build_lead_graph(),
            InMemorySaver(),
            self.llm,
            tracing,
            self._recording_tools(search or ListingSearch()),
        )
        tenant_id = uuid4()
        self.thread = Thread(
            uuid4(),
            ThreadKey(tenant_id, Channel.SIMULATOR, "visitor.1"),
            3,
            ThreadStatus.OPEN,
            datetime.now(UTC),
            None,
        )
        self.business = BusinessContext(tenant_id, "Inmobiliaria Sur", TIMEZONE, team_hours)
        self.now = now
        self.turns: list[list[dict[str, Any]]] = []
        self.last_state: dict[str, Any] = {}

    def _recording_tools(self, search: ListingSearch):
        handlers = lead_handlers(search)
        registry = lead_tools(search)

        def record(name: str):
            def call(arguments: Any) -> Any:
                self.tool_calls.append(name)
                return handlers[name](arguments)

            return call

        return registry.wrapped(lambda tool: record(tool.name))

    def say(self, text: str, choice_id: str | None = None) -> list[dict[str, Any]]:
        turn = self.runtime.handle(
            self.thread,
            TurnInput(
                self.config,
                self.business,
                [],
                text,
                now=self.now,
                choice_id=choice_id,
                visitor_contact=self.visitor_contact,
            ),
        )
        messages = [
            {
                "text": m.text,
                "author": m.author.value,
                "cards": (m.payload or {}).get("cards"),
                "slots": (m.payload or {}).get("slots"),
            }
            for m in turn.outbound
        ]
        self.turns.append(messages)
        self.last_state = dict(turn.state)
        return messages

    def state(self) -> dict[str, Any]:
        return dict(self.runtime.state(self.thread.key))

    def asked(self) -> list[str]:
        """Question keys in the order the agent asked them."""
        return [r.question.key for r in self.llm.replies if r.question is not None]

    def intents(self) -> list[str]:
        return [r.intent.value for r in self.llm.replies]

    def all_messages(self) -> list[dict[str, Any]]:
        return [message for turn in self.turns for message in turn]
