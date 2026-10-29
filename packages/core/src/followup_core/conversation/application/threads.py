from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from followup_core.tenancy.domain.agent_config import AgentConfig

from ..domain.llm import TranscriptLine
from ..domain.repositories import MessageRepository, ThreadLock, ThreadRepository
from ..domain.runtime import AgentRuntime, TurnInput, TurnMetrics
from ..domain.thread import (
    Author,
    Direction,
    Message,
    Thread,
    ThreadKey,
    ThreadStatus,
    clean_inbound_text,
)
from .ports import AgentConfigSource, BusinessContextSource

TRANSCRIPT_WINDOW = 12

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class HandledTurn:
    thread: Thread
    outbound: Sequence[Message]
    state: Mapping[str, Any]
    agent_config: AgentConfig
    metrics: TurnMetrics
    trace_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ThreadView:
    thread: Thread | None
    messages: Sequence[Message]
    state: Mapping[str, Any]
    agent_config: AgentConfig
    current_version: int

    @property
    def config_outdated(self) -> bool:
        return self.thread is not None and self.thread.agent_config_version < self.current_version


def _new_thread(
    key: ThreadKey, version: int, started_by_profile_id: UUID | None, now: datetime
) -> Thread:
    return Thread(
        id=uuid4(),
        key=key,
        agent_config_version=version,
        status=ThreadStatus.OPEN,
        created_at=now,
        last_message_at=None,
        started_by_profile_id=started_by_profile_id,
    )


class HandleIncomingMessage:
    """Channel-agnostic: one inbound message in, the agent's outbound messages out.

    Nothing is written until the agent has replied, and the caller's transaction also covers
    the lock and the graph checkpoint, so a failed turn (for example an LLM timeout) leaves
    nothing behind.
    """

    def __init__(
        self,
        threads: ThreadRepository,
        messages: MessageRepository,
        lock: ThreadLock,
        runtime: AgentRuntime,
        configs: AgentConfigSource,
        business: BusinessContextSource,
        clock: Clock = utc_now,
    ) -> None:
        self._threads = threads
        self._messages = messages
        self._lock = lock
        self._runtime = runtime
        self._configs = configs
        self._business = business
        self._clock = clock

    def execute(
        self, key: ThreadKey, text: str, started_by_profile_id: UUID | None = None
    ) -> HandledTurn:
        text = clean_inbound_text(text)
        self._lock.acquire(key)

        thread = self._threads.get_by_key(key)
        is_new = thread is None
        if thread is None:
            version, _ = self._configs.current(key.tenant_id)
            thread = _new_thread(key, version, started_by_profile_id, self._clock())
        history = [] if is_new else self._messages.list_for_thread(thread.id)
        config = self._configs.at_version(key.tenant_id, thread.agent_config_version)

        # Run the agent before writing anything: if it fails, no thread, inbound message or
        # partial reply is stored.
        turn = self._runtime.handle(
            thread,
            TurnInput(
                agent_config=config,
                business=self._business(key.tenant_id),
                transcript=[
                    TranscriptLine(message.author, message.text)
                    for message in history[-TRANSCRIPT_WINDOW:]
                ],
                text=text,
            ),
        )

        if is_new:
            self._threads.add(thread)
        self._messages.append(
            Message(uuid4(), thread.id, Direction.INBOUND, Author.VISITOR, text, self._clock())
        )
        outbound: list[Message] = []
        for item in turn.outbound:
            message = Message(
                uuid4(),
                thread.id,
                Direction.OUTBOUND,
                Author.AGENT,
                item.text,
                self._clock(),
                item.payload,
                turn.trace_run_id,
            )
            self._messages.append(message)
            outbound.append(message)
        self._threads.touch(thread.id, self._clock())

        return HandledTurn(thread, outbound, turn.state, config, turn.metrics, turn.trace_run_id)


class GetThread:
    """Transcript from our own tables, state from the runtime. Creates nothing."""

    def __init__(
        self,
        threads: ThreadRepository,
        messages: MessageRepository,
        runtime: AgentRuntime,
        configs: AgentConfigSource,
    ) -> None:
        self._threads = threads
        self._messages = messages
        self._runtime = runtime
        self._configs = configs

    def execute(self, tenant_id: UUID, key: ThreadKey | None) -> ThreadView:
        current_version, current_config = self._configs.current(tenant_id)
        thread = self._threads.get_by_key(key) if key else None
        if thread is None:
            return ThreadView(None, [], {}, current_config, current_version)
        return ThreadView(
            thread=thread,
            messages=self._messages.list_for_thread(thread.id),
            state=self._runtime.state(thread.key),
            agent_config=self._configs.at_version(tenant_id, thread.agent_config_version),
            current_version=current_version,
        )


class StartNewThread:
    """Opens an empty thread pinned to the current agent config (used by Reiniciar)."""

    def __init__(
        self,
        threads: ThreadRepository,
        lock: ThreadLock,
        configs: AgentConfigSource,
        clock: Clock = utc_now,
    ) -> None:
        self._threads = threads
        self._lock = lock
        self._configs = configs
        self._clock = clock

    def execute(self, key: ThreadKey, started_by_profile_id: UUID | None = None) -> Thread:
        self._lock.acquire(key)
        existing = self._threads.get_by_key(key)
        if existing is not None:
            return existing
        version, _ = self._configs.current(key.tenant_id)
        thread = _new_thread(key, version, started_by_profile_id, self._clock())
        self._threads.add(thread)
        return thread
