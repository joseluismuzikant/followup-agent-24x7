"""The parts of the runtime contract products build on: tools, system messages, the turn
clock, turn observers and choice extraction."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

import pytest
from conversation_fakes import (
    InMemoryMessageRepository,
    InMemoryThreadRepository,
    RecordingLock,
    StaticConfigSource,
    agent_config,
    business,
)
from followup_core.conversation.application.threads import HandledTurn, HandleIncomingMessage
from followup_core.conversation.domain.llm import Choice, ExtractionRequest
from followup_core.conversation.domain.thread import Author, Channel, ThreadKey
from followup_core.conversation.domain.tools import Tool, ToolRegistry, UnknownToolError
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.langgraph_runtime import (
    GraphContext,
    LangGraphRuntime,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime


@dataclass(frozen=True, slots=True)
class Shout:
    text: str


class ToolState(TypedDict):
    inbound: str
    outbox: list[dict[str, Any]]
    seen_at: NotRequired[str]


def tool_graph() -> StateGraph[Any, Any, Any, Any]:
    def respond(state: ToolState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
        context = runtime.context
        loud = context.tools.call("shout", Shout(state["inbound"]))
        outbox: list[dict[str, Any]] = [{"text": loud, "payload": None}]
        if state["inbound"] == "derivar":
            outbox.append({"text": "Evento", "payload": None, "author": "system"})
        return {"outbox": outbox, "seen_at": context.turn.now.isoformat()}

    graph = StateGraph(ToolState, context_schema=GraphContext)
    graph.add_node("respond", respond)
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    return graph


def shout_registry(calls: list[str]) -> ToolRegistry:
    def shout(arguments: Shout) -> str:
        calls.append(arguments.text)
        return arguments.text.upper()

    return ToolRegistry([Tool("shout", "Repeats the text in capitals.", Shout, shout)])


class Recorder:
    def __init__(self) -> None:
        self.turns: list[HandledTurn] = []

    def on_turn(self, turn: HandledTurn) -> None:
        self.turns.append(turn)


def _handle(calls: list[str], recorder: Recorder, now: datetime) -> HandleIncomingMessage:
    threads = InMemoryThreadRepository()
    runtime = LangGraphRuntime(
        tool_graph(), InMemorySaver(), FakeLanguageModel(), tools=shout_registry(calls)
    )
    return HandleIncomingMessage(
        threads,
        InMemoryMessageRepository(threads),
        RecordingLock(),
        runtime,
        StaticConfigSource(agent_config()),
        business,
        clock=lambda: now,
        observers=[recorder],
    )


def test_graph_tools_system_messages_clock_and_observers() -> None:
    calls: list[str] = []
    recorder = Recorder()
    now = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
    handle = _handle(calls, recorder, now)
    key = ThreadKey(uuid4(), Channel.SIMULATOR, "v1")

    first = handle.execute(key, "hola")
    second = handle.execute(key, "derivar")

    assert calls == ["hola", "derivar"]
    assert [m.text for m in first.outbound] == ["HOLA"]
    assert [(m.author, m.text) for m in second.outbound] == [
        (Author.AGENT, "DERIVAR"),
        (Author.SYSTEM, "Evento"),
    ]
    assert second.state["seen_at"] == now.isoformat()
    assert [turn.started_thread for turn in recorder.turns] == [True, False]
    assert recorder.turns[1].inbound.text == "derivar"


def test_an_observer_error_fails_the_turn() -> None:
    class Failing:
        def on_turn(self, turn: HandledTurn) -> None:
            raise RuntimeError("boom")

    threads = InMemoryThreadRepository()
    handle = HandleIncomingMessage(
        threads,
        InMemoryMessageRepository(threads),
        RecordingLock(),
        LangGraphRuntime(
            tool_graph(), InMemorySaver(), FakeLanguageModel(), tools=shout_registry([])
        ),
        StaticConfigSource(agent_config()),
        business,
        observers=[Failing()],
    )

    with pytest.raises(RuntimeError):
        handle.execute(ThreadKey(uuid4(), Channel.SIMULATOR, "v1"), "hola")


def test_registry_rejects_duplicates_unknown_tools_and_wrong_inputs() -> None:
    registry = shout_registry([])

    assert registry.names == frozenset({"shout"})
    assert registry.get("shout").input_schema == {"text": "str"}
    with pytest.raises(ValueError, match="declared twice"):
        ToolRegistry([registry.get("shout"), registry.get("shout")])
    with pytest.raises(UnknownToolError):
        registry.call("missing", Shout("x"))
    with pytest.raises(TypeError):
        registry.call("shout", {"text": "x"})


CARDS = [
    Choice("a", "2 ambientes luminoso · Gorriti 4800, Palermo"),
    Choice("b", "3 ambientes con cochera · Guatemala 5200, Palermo"),
]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Me interesa la segunda", "b"),
        ("la 1", "a"),
        ("Me gusta la de Gorriti", "a"),
        ("2 ambientes luminoso · Gorriti 4800, Palermo", "a"),
        ("Quiero 2 ambientes", None),
        ("Las dos me gustan, en Palermo", None),
    ],
)
def test_fake_model_picks_a_choice_by_position_label_or_address(
    text: str, expected: str | None
) -> None:
    result = FakeLanguageModel().extract(ExtractionRequest([], [], text, choices=CARDS))

    assert result.choice_id == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Prefiero hablar con una persona", True),
        ("¿Puedo hablar con alguien del equipo?", True),
        ("Quiero hablar con un asesor", True),
        ("Quiero alquilar en Palermo", False),
    ],
)
def test_fake_model_detects_a_request_for_a_person(text: str, expected: bool) -> None:
    assert FakeLanguageModel().extract(ExtractionRequest([], [], text)).wants_human is expected
