"""In-memory repositories and a tiny echo graph shared by the conversation unit tests.

Core has no product graph, so the tests run a minimal one through the real LangGraph
runtime with an in-memory checkpointer.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, NotRequired, TypedDict
from uuid import UUID

from followup_core.conversation.domain.llm import ReplyIntent, ReplyRequest
from followup_core.conversation.domain.runtime import BusinessContext
from followup_core.conversation.domain.thread import (
    Channel,
    Direction,
    Message,
    Thread,
    ThreadKey,
)
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.langgraph_runtime import (
    GraphContext,
    LangGraphRuntime,
)
from followup_core.tenancy.domain.agent_config import (
    AfterHoursMode,
    AgentConfig,
    QualificationQuestion,
    QuestionKind,
    Tone,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime


class InMemoryThreadRepository:
    def __init__(self) -> None:
        self.threads: dict[str, Thread] = {}

    def get_by_key(self, key: ThreadKey) -> Thread | None:
        return self.threads.get(str(key))

    def _started_by(self, tenant_id: UUID, channel: Channel, profile_id: UUID) -> list[Thread]:
        return [
            thread
            for thread in self.threads.values()
            if (thread.tenant_id, thread.channel, thread.started_by_profile_id)
            == (tenant_id, channel, profile_id)
        ]

    def count_started_by(self, tenant_id: UUID, channel: Channel, profile_id: UUID) -> int:
        return len(self._started_by(tenant_id, channel, profile_id))

    def add(self, thread: Thread) -> None:
        self.threads[str(thread.key)] = thread

    def touch(self, thread_id: UUID, last_message_at: datetime) -> None:
        for key, thread in self.threads.items():
            if thread.id == thread_id:
                from dataclasses import replace

                self.threads[key] = replace(thread, last_message_at=last_message_at)


class InMemoryMessageRepository:
    def __init__(self, threads: InMemoryThreadRepository) -> None:
        self.messages: list[Message] = []
        self._threads = threads

    def append(self, message: Message) -> None:
        self.messages.append(message)

    def list_for_thread(self, thread_id: UUID) -> Sequence[Message]:
        return [message for message in self.messages if message.thread_id == thread_id]

    def count_inbound_since(self, tenant_id: UUID, channel: Channel, since: datetime) -> int:
        threads = {
            thread.id
            for thread in self._threads.threads.values()
            if thread.tenant_id == tenant_id and thread.channel == channel
        }
        return sum(
            1
            for message in self.messages
            if message.thread_id in threads
            and message.direction is Direction.INBOUND
            and message.created_at >= since
        )


class RecordingLock:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def acquire(self, key: ThreadKey) -> None:
        self.keys.append(str(key))


class StaticConfigSource:
    """Version 0 is the defaults; `save` adds a new version."""

    def __init__(self, config: AgentConfig) -> None:
        self.versions: dict[int, AgentConfig] = {0: config}

    def save(self, config: AgentConfig) -> int:
        version = max(self.versions) + 1
        self.versions[version] = config
        return version

    def current(self, tenant_id: UUID) -> tuple[int, AgentConfig]:
        version = max(self.versions)
        return version, self.versions[version]

    def at_version(self, tenant_id: UUID, version: int) -> AgentConfig:
        return self.versions[version]


def agent_config(agent_name: str = "Sofía") -> AgentConfig:
    return AgentConfig(
        agent_name=agent_name,
        tone=Tone.WARM,
        after_hours_mode=AfterHoursMode.KEEP_ANSWERING_AND_PROPOSE_VISIT,
        qualification_questions=(QualificationQuestion("zone", "Zona", QuestionKind.TEXT),),
    )


def business(tenant_id: UUID) -> BusinessContext:
    return BusinessContext(tenant_id, "Inmobiliaria Sur", "America/Argentina/Buenos_Aires")


class EchoState(TypedDict):
    inbound: str
    outbox: list[dict[str, Any]]
    count: NotRequired[int]
    agent_name: NotRequired[str]


def echo_graph() -> StateGraph[Any, Any, Any, Any]:
    def respond(state: EchoState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
        config = runtime.context.turn.agent_config
        reply = runtime.context.llm.compose_reply(
            ReplyRequest(ReplyIntent.ASK_NAME, Tone.WARM, config.agent_name, "Sur")
        )
        count = state.get("count", 0) + 1
        return {
            "count": count,
            "agent_name": config.agent_name,
            "outbox": [{"text": f"{count}: {reply.text}", "payload": None}],
        }

    graph = StateGraph(EchoState, context_schema=GraphContext)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph


def echo_runtime(llm: FakeLanguageModel | None = None) -> LangGraphRuntime:
    return LangGraphRuntime(echo_graph(), InMemorySaver(), llm or FakeLanguageModel())
