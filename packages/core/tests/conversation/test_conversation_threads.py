from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conversation_fakes import (
    InMemoryMessageRepository,
    InMemoryThreadRepository,
    RecordingLock,
    StaticConfigSource,
    agent_config,
    business,
    echo_runtime,
)
from followup_core.conversation.application.simulator import (
    GetSimulator,
    ResetSimulator,
    SendSimulatorMessage,
    simulator_key,
)
from followup_core.conversation.application.threads import (
    GetThread,
    HandleIncomingMessage,
    StartNewThread,
)
from followup_core.conversation.domain.errors import (
    InvalidMessageError,
    LlmUnavailableError,
    SimulatorLimitReachedError,
)
from followup_core.conversation.domain.thread import Author, Channel, Direction, ThreadKey
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel


class World:
    def __init__(self, llm: FakeLanguageModel | None = None, daily_limit: int = 300) -> None:
        self.tenant_id = uuid4()
        self.profile_id = uuid4()
        self.threads = InMemoryThreadRepository()
        self.messages = InMemoryMessageRepository(self.threads)
        self.lock = RecordingLock()
        self.configs = StaticConfigSource(agent_config())
        self.runtime = echo_runtime(llm)
        self.now = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
        self.handle = HandleIncomingMessage(
            self.threads,
            self.messages,
            self.lock,
            self.runtime,
            self.configs,
            business,
            clock=lambda: self.now,
        )
        self.get_thread = GetThread(self.threads, self.messages, self.runtime, self.configs)
        self.start = StartNewThread(self.threads, self.lock, self.configs, clock=lambda: self.now)
        self.send = SendSimulatorMessage(
            self.threads, self.messages, self.handle, business, daily_limit, lambda: self.now
        )
        self.get = GetSimulator(self.threads, self.get_thread)
        self.reset = ResetSimulator(self.threads, self.start, self.get_thread)

    def key(self, visitor: str = "visitor-1") -> ThreadKey:
        return ThreadKey(self.tenant_id, Channel.SIMULATOR, visitor)


def test_thread_key_has_the_canonical_format() -> None:
    tenant_id = uuid4()

    assert str(ThreadKey(tenant_id, Channel.WHATSAPP, "5491100000000")) == (
        f"{tenant_id}:whatsapp:5491100000000"
    )
    assert str(simulator_key(tenant_id, tenant_id, 3)).endswith(f":simulator:{tenant_id}.3")
    with pytest.raises(ValueError):
        ThreadKey(tenant_id, Channel.SIMULATOR, "has:colon")


def test_handle_stores_inbound_and_outbound_and_takes_the_lock() -> None:
    world = World()

    turn = world.handle.execute(world.key(), "  hola  ")

    stored = world.messages.list_for_thread(turn.thread.id)
    assert [(m.direction, m.author, m.text) for m in stored] == [
        (Direction.INBOUND, Author.VISITOR, "hola"),
        (Direction.OUTBOUND, Author.AGENT, "1: ¿Cómo te llamás?"),
    ]
    assert [m.id for m in turn.outbound] == [stored[1].id]
    assert world.lock.keys == [str(world.key())]
    assert world.threads.get_by_key(world.key()).last_message_at == world.now  # type: ignore[union-attr]
    assert turn.state["count"] == 1


def test_the_state_continues_across_turns() -> None:
    world = World()
    world.handle.execute(world.key(), "uno")

    second = world.handle.execute(world.key(), "dos")

    assert second.state["count"] == 2
    assert world.runtime.state(world.key())["count"] == 2
    assert len(world.messages.messages) == 4


def test_a_thread_keeps_the_config_version_it_started_with() -> None:
    world = World()
    world.handle.execute(world.key(), "hola")
    world.configs.save(agent_config("Lucía"))

    old = world.handle.execute(world.key(), "sigo")
    new = world.handle.execute(world.key("visitor-2"), "hola")

    assert (old.thread.agent_config_version, old.state["agent_name"]) == (0, "Sofía")
    assert (new.thread.agent_config_version, new.state["agent_name"]) == (1, "Lucía")
    assert world.get_thread.execute(world.tenant_id, world.key()).config_outdated is True
    assert (
        world.get_thread.execute(world.tenant_id, world.key("visitor-2")).config_outdated is False
    )


def test_a_failed_turn_leaves_nothing_behind() -> None:
    world = World(FakeLanguageModel(fail_with=TimeoutError()))

    with pytest.raises(LlmUnavailableError):
        world.handle.execute(world.key(), "hola")

    assert world.threads.threads == {}
    assert world.messages.messages == []
    assert world.runtime.state(world.key()) == {}


def test_a_failed_turn_on_an_existing_thread_keeps_the_previous_state() -> None:
    llm = FakeLanguageModel()
    world = World(llm)
    world.handle.execute(world.key(), "uno")
    llm.fail_with = TimeoutError()

    with pytest.raises(LlmUnavailableError):
        world.handle.execute(world.key(), "dos")

    assert len(world.messages.messages) == 2
    assert world.runtime.state(world.key())["count"] == 1


@pytest.mark.parametrize("text", ["", "   ", "x" * 1001])
def test_messages_must_have_1_to_1000_characters(text: str) -> None:
    world = World()

    with pytest.raises(InvalidMessageError):
        world.handle.execute(world.key(), text)


def test_get_thread_creates_nothing() -> None:
    world = World()

    view = world.get_thread.execute(world.tenant_id, world.key())

    assert (view.thread, view.messages, view.state) == (None, [], {})
    assert view.agent_config.agent_name == "Sofía"
    assert world.threads.threads == {}


def test_start_new_thread_pins_the_current_version_and_is_idempotent() -> None:
    world = World()
    world.configs.save(agent_config("Lucía"))

    first = world.start.execute(world.key(), started_by_profile_id=world.profile_id)
    again = world.start.execute(world.key(), started_by_profile_id=world.profile_id)

    assert first == again
    assert first.agent_config_version == 1


def test_simulator_reset_opens_the_next_numbered_thread() -> None:
    world = World()
    first = world.send.execute(world.tenant_id, world.profile_id, "hola")

    reset = world.reset.execute(world.tenant_id, world.profile_id)
    after = world.send.execute(world.tenant_id, world.profile_id, "de nuevo")

    assert first.thread.visitor_id == f"{world.profile_id}.1"
    assert reset.thread is not None
    assert reset.thread.visitor_id == f"{world.profile_id}.2"
    assert reset.messages == []
    assert after.thread.key == reset.thread.key
    assert after.state["count"] == 1
    assert world.get.execute(world.tenant_id, world.profile_id).thread == world.threads.get_by_key(
        reset.thread.key
    )


def test_simulator_daily_limit_counts_today_in_the_tenant_timezone() -> None:
    world = World(daily_limit=2)
    world.send.execute(world.tenant_id, world.profile_id, "uno")
    world.send.execute(world.tenant_id, world.profile_id, "dos")

    with pytest.raises(SimulatorLimitReachedError):
        world.send.execute(world.tenant_id, world.profile_id, "tres")

    # 15:00 UTC is noon in Buenos Aires; the next local day starts at 03:00 UTC.
    world.now = world.now + timedelta(hours=12, minutes=1)
    assert world.send.execute(world.tenant_id, world.profile_id, "mañana").state["count"] == 3
