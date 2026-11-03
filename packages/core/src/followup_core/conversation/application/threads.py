from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from followup_core.tenancy.domain.agent_config import AgentConfig

from ..domain.llm import TranscriptLine
from ..domain.repositories import MessageRepository, ThreadLock, ThreadRepository
from ..domain.runtime import AgentRuntime, TurnInput, TurnMetrics
from ..domain.thread import (
    MAX_MESSAGE_LENGTH,
    Author,
    Direction,
    InboundPart,
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
    # The last inbound message of the turn; `inbound_messages` has all of them, in order.
    inbound: Message
    outbound: Sequence[Message]
    state: Mapping[str, Any]
    agent_config: AgentConfig
    metrics: TurnMetrics
    # True when this message opened the thread.
    started_thread: bool = False
    trace_run_id: UUID | None = None
    inbound_messages: Sequence[Message] = ()


class TurnObserver(Protocol):
    """Called after a turn is stored, inside the same transaction (the product records its
    own view of the conversation, such as a lead). Raising rolls the whole turn back."""

    def on_turn(self, turn: HandledTurn) -> None: ...


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
        observers: Sequence[TurnObserver] = (),
    ) -> None:
        self._threads = threads
        self._messages = messages
        self._lock = lock
        self._runtime = runtime
        self._configs = configs
        self._business = business
        self._clock = clock
        self._observers = observers

    def execute(
        self,
        key: ThreadKey,
        text: str | Sequence[InboundPart],
        started_by_profile_id: UUID | None = None,
        *,
        choice_id: str | None = None,
        visitor_contact: str | None = None,
    ) -> HandledTurn:
        """One turn for one message, or for a burst of them (`InboundPart`s, each stored on
        its own; the agent reads their texts joined, in order)."""
        parts = [InboundPart(text)] if isinstance(text, str) else list(text)
        # What the agent cannot read (media in a burst) is stored but not given to it.
        stored = [
            clean_inbound_text(part.text)
            if part.content_type == "text"
            else part.text.strip()[:MAX_MESSAGE_LENGTH]
            for part in parts
        ]
        texts = [
            value for part, value in zip(parts, stored, strict=True) if part.content_type == "text"
        ]
        if not texts:
            raise ValueError("A turn needs at least one text message.")
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
        received_at = self._clock()
        text = "\n".join(texts)
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
                now=received_at,
                choice_id=choice_id,
                visitor_contact=visitor_contact,
            ),
        )

        if is_new:
            self._threads.add(thread)
        inbound_messages = [
            Message(
                uuid4(),
                thread.id,
                Direction.INBOUND,
                Author.VISITOR,
                part_text,
                part.received_at or received_at,
                content_type=part.content_type,
            )
            for part, part_text in zip(parts, stored, strict=True)
        ]
        for message in inbound_messages:
            self._messages.append(message)
        inbound = inbound_messages[-1]
        outbound: list[Message] = []
        for item in turn.outbound:
            message = Message(
                uuid4(),
                thread.id,
                Direction.OUTBOUND,
                item.author,
                item.text,
                self._clock(),
                item.payload,
                turn.trace_run_id,
            )
            self._messages.append(message)
            outbound.append(message)
        self._threads.touch(thread.id, self._clock())

        handled = HandledTurn(
            thread=thread,
            inbound=inbound,
            outbound=outbound,
            state=turn.state,
            agent_config=config,
            metrics=turn.metrics,
            started_thread=is_new,
            trace_run_id=turn.trace_run_id,
            inbound_messages=inbound_messages,
        )
        for observer in self._observers:
            observer.on_turn(handled)
        return handled


@dataclass(frozen=True, slots=True)
class FixedReply:
    thread: Thread
    inbound_messages: Sequence[Message]
    outbound: Message


class ReplyWithoutAgent:
    """Stores what the agent cannot read (audio, images, ...) and a fixed reply, without
    running the agent or calling the model. Same lock and thread rules as a turn."""

    def __init__(
        self,
        threads: ThreadRepository,
        messages: MessageRepository,
        lock: ThreadLock,
        configs: AgentConfigSource,
        clock: Clock = utc_now,
    ) -> None:
        self._threads = threads
        self._messages = messages
        self._lock = lock
        self._configs = configs
        self._clock = clock

    def execute(self, key: ThreadKey, parts: Sequence[InboundPart], reply: str) -> FixedReply:
        self._lock.acquire(key)
        now = self._clock()
        thread = self._threads.get_by_key(key)
        if thread is None:
            version, _ = self._configs.current(key.tenant_id)
            thread = _new_thread(key, version, None, now)
            self._threads.add(thread)
        inbound = [
            Message(
                uuid4(),
                thread.id,
                Direction.INBOUND,
                Author.VISITOR,
                part.text.strip()[:MAX_MESSAGE_LENGTH],
                part.received_at or now,
                content_type=part.content_type,
            )
            for part in parts
        ]
        for message in inbound:
            self._messages.append(message)
        outbound = Message(uuid4(), thread.id, Direction.OUTBOUND, Author.AGENT, reply, now)
        self._messages.append(outbound)
        self._threads.touch(thread.id, now)
        return FixedReply(thread, inbound, outbound)


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
