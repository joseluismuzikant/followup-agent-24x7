"""Takeover in the Conversation context: control changes write system events, a taken-over
thread stores the visitor's messages without running the agent, team messages need control,
and the first turn after a release reads what the visitor told the team."""

from uuid import uuid4

import pytest
from conversation_fakes import InMemoryMessageRepository
from followup_core.conversation.application.control import (
    Actor,
    AddTeamMessage,
    ReleaseThread,
    TakeOverThread,
)
from followup_core.conversation.application.threads import ReplyWithoutAgent
from followup_core.conversation.domain.errors import ConversationNotTakenError, InvalidMessageError
from followup_core.conversation.domain.thread import (
    Author,
    Control,
    InboundPart,
    release,
    take_over,
)
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from test_conversation_threads import World

ANA = Actor(uuid4(), "Ana")


class Takeover(World):
    def __init__(self, llm: FakeLanguageModel | None = None) -> None:
        super().__init__(llm)
        clock = lambda: self.now  # noqa: E731
        self.take = TakeOverThread(self.threads, self.messages, self.lock, clock)
        self.give_back = ReleaseThread(self.threads, self.messages, self.lock, clock)
        self.write = AddTeamMessage(self.threads, self.messages, self.lock, clock)

    def texts(self) -> list[tuple[Author, str]]:
        assert isinstance(self.messages, InMemoryMessageRepository)
        return [(message.author, message.text) for message in self.messages.messages]


def test_take_over_and_release_return_the_thread_and_an_event() -> None:
    world = Takeover()
    thread = world.handle.execute(world.key(), "hola").thread

    taken, event = take_over(thread, ANA.profile_id, "Ana", world.now)
    released, back = release(taken, "Ana", world.now)

    assert (taken.control, taken.controlled_by_profile_id) == (Control.HUMAN, ANA.profile_id)
    assert (event.author, event.text) == (Author.SYSTEM, "Ana tomó la conversación")
    assert (released.control, released.controlled_by_profile_id) == (Control.AGENT, None)
    assert back is not None and back.text == "Ana devolvió la conversación al agente"
    assert release(released, "Ana", world.now) == (released, None)


def test_a_taken_over_thread_stores_messages_without_the_agent() -> None:
    world = Takeover()
    thread = world.handle.execute(world.key(), "hola").thread
    world.take.execute(thread.id, ANA)

    turn = world.handle.execute(world.key(), "¿hay alguien?")

    assert turn.agent_paused and list(turn.outbound) == [] and dict(turn.state) == {}
    assert world.texts()[-2:] == [
        (Author.SYSTEM, "Ana tomó la conversación"),
        (Author.VISITOR, "¿hay alguien?"),
    ]
    # Every control change and turn takes the same per-thread lock.
    assert world.lock.keys.count(str(world.key())) == 3


def test_media_under_takeover_gets_no_fixed_reply() -> None:
    world = Takeover()
    thread = world.handle.execute(world.key(), "hola").thread
    world.take.execute(thread.id, ANA)
    reply = ReplyWithoutAgent(world.threads, world.messages, world.lock, world.configs)

    fixed = reply.execute(world.key(), [InboundPart("", content_type="audio")], "Por ahora…")

    assert fixed.outbound is None
    assert world.texts()[-1] == (Author.VISITOR, "")


def test_team_messages_need_control_unless_the_action_says_otherwise() -> None:
    world = Takeover()
    thread = world.handle.execute(world.key(), "hola").thread

    with pytest.raises(ConversationNotTakenError):
        world.write.execute(thread.id, ANA, "Hola, soy Ana")
    with pytest.raises(InvalidMessageError):
        world.write.execute(thread.id, ANA, "   ", require_control=False)
    confirmation = world.write.execute(thread.id, ANA, "Te confirmamos", require_control=False)
    world.take.execute(thread.id, ANA)
    reply = world.write.execute(thread.id, ANA, "Hola, soy Ana")

    assert (confirmation.author, confirmation.author_profile_id) == (Author.HUMAN, ANA.profile_id)
    assert reply.text == "Hola, soy Ana"


def test_taking_it_again_is_a_no_op_but_another_person_moves_control() -> None:
    world = Takeover()
    thread = world.handle.execute(world.key(), "hola").thread
    world.take.execute(thread.id, ANA)

    assert world.take.execute(thread.id, ANA).event is None
    luis = Actor(uuid4(), "Luis")
    change = world.take.execute(thread.id, luis)

    assert change.thread.controlled_by_profile_id == luis.profile_id
    assert change.event is not None and change.event.text == "Luis tomó la conversación"


def test_after_a_release_the_agent_reads_what_the_visitor_told_the_team() -> None:
    world = Takeover()
    thread = world.handle.execute(world.key(), "hola").thread
    world.take.execute(thread.id, ANA)
    world.write.execute(thread.id, ANA, "¿En qué zona buscás?")
    world.handle.execute(world.key(), "En Palermo")
    world.give_back.execute(thread.id, ANA)

    turn = world.handle.execute(world.key(), "¿Seguimos?")

    # The agent answers again. (What it reads is checked with the lead graph in the API
    # tests: the team's lines in the transcript, the visitor's unread lines in `latest`.)
    assert not turn.agent_paused and turn.outbound
    assert (Author.HUMAN, "¿En qué zona buscás?") in world.texts()
