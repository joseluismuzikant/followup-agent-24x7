"""The inmo24x7 qualification graph, run through the real LangGraph runtime with the fake LLM
and an in-memory checkpointer. The flow must not depend on the model."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from followup_core.conversation.domain.llm import ReplyIntent, ReplyRequest
from followup_core.conversation.domain.runtime import BusinessContext, TurnInput
from followup_core.conversation.domain.thread import Channel, Thread, ThreadKey, ThreadStatus
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.langgraph_runtime import LangGraphRuntime
from followup_core.tenancy.domain.agent_config import (
    AgentConfig,
    QualificationQuestion,
    QuestionKind,
    Tone,
)
from inmo24x7_api.defaults import build_setup_defaults
from inmo24x7_api.leads.display import known_rows
from inmo24x7_api.leads.graph import build_lead_graph
from inmo24x7_api.leads.properties import SamplePropertySearch
from langgraph.checkpoint.memory import InMemorySaver

DEFAULTS = build_setup_defaults().agent_config


class RecordingLlm(FakeLanguageModel):
    def __init__(self) -> None:
        super().__init__()
        self.replies: list[ReplyRequest] = []

    def compose_reply(self, request: ReplyRequest):
        self.replies.append(request)
        return super().compose_reply(request)


class Chat:
    def __init__(self, config: AgentConfig = DEFAULTS) -> None:
        self.config = config
        self.llm = RecordingLlm()
        self.runtime = LangGraphRuntime(
            build_lead_graph(SamplePropertySearch()), InMemorySaver(), self.llm
        )
        tenant_id = uuid4()
        self.thread = Thread(
            uuid4(),
            ThreadKey(tenant_id, Channel.SIMULATOR, "visitor.1"),
            0,
            ThreadStatus.OPEN,
            datetime.now(UTC),
            None,
        )
        self.business = BusinessContext(tenant_id, "Inmobiliaria Sur", "UTC")
        self.turns: list[list[dict]] = []

    def say(self, text: str) -> list[dict]:
        turn = self.runtime.handle(self.thread, TurnInput(self.config, self.business, [], text))
        messages = [
            {"text": m.text, "cards": (m.payload or {}).get("cards")} for m in turn.outbound
        ]
        self.turns.append(messages)
        return messages

    def state(self) -> dict:
        return dict(self.runtime.state(self.thread.key))

    def asked(self) -> list[str]:
        """Question keys in the order the agent asked them."""
        return [r.question.key for r in self.llm.replies if r.question is not None]

    def intents(self) -> list[str]:
        return [r.intent.value for r in self.llm.replies]


def _config(*questions: QualificationQuestion, tone: Tone = Tone.WARM) -> AgentConfig:
    return replace(DEFAULTS, qualification_questions=questions, tone=tone)


def _question(key: str) -> QualificationQuestion:
    return next(q for q in DEFAULTS.qualification_questions if q.key == key)


SCRIPT = [
    "Hola",
    "Quiero alquilar",
    "Palermo",
    "hasta 800 mil pesos",
    "no",
    "2",
    "me llamo Ana Pérez",
    "ana@example.com",
]


def test_greets_with_the_configured_name_and_business() -> None:
    chat = Chat()

    (greeting,) = chat.say("Hola")

    assert greeting["text"].startswith("¡Hola! Soy Sofía, de Inmobiliaria Sur.")
    assert chat.asked() == ["operation"]


def test_one_question_per_message_in_config_order() -> None:
    chat = Chat()
    for text in SCRIPT:
        chat.say(text)

    assert chat.asked() == ["operation", "zone", "budget", "mortgage_approved", "rooms"]
    for request in chat.llm.replies:
        if request.question is not None:
            assert request.intent in (ReplyIntent.GREET, ReplyIntent.ASK)
    # Only one message per turn carries a question.
    for messages in chat.turns:
        assert sum(text.count("?") for text in (m["text"] for m in messages)) <= 1


def test_order_follows_the_config_and_disabled_questions_are_skipped() -> None:
    chat = Chat(
        _config(
            _question("zone"),
            replace(_question("budget"), enabled=False),
            _question("operation"),
            _question("rooms"),
        )
    )
    for text in ["Hola", "Belgrano", "comprar", "3"]:
        chat.say(text)

    assert chat.asked() == ["zone", "operation", "rooms"]
    assert "budget" not in chat.state()["answers"]
    assert [row.key for row in known_rows(chat.config, chat.state())] == [
        "zone",
        "operation",
        "rooms",
        "visitor_name",
        "contact",
    ]


def test_custom_questions_are_asked_and_stored_but_never_filter() -> None:
    pets = QualificationQuestion("custom_1", "Si tiene mascotas", QuestionKind.BOOLEAN)
    chat = Chat(_config(_question("operation"), pets, _question("zone")))
    chat.say("Hola")
    chat.say("Quiero comprar")
    chat.say("sí")
    (cards_message, _) = chat.say("Caballito")

    assert chat.asked() == ["operation", "custom_1", "zone"]
    assert chat.state()["answers"]["custom_1"] is True
    assert [card["id"] for card in cards_message["cards"]] == ["caballito-acoyte-2amb"]


def test_cards_come_before_asking_for_name_or_contact() -> None:
    chat = Chat()
    for text in SCRIPT:
        chat.say(text)

    intents = chat.intents()
    shown = intents.index("present_options")
    assert shown < intents.index("ask_name") < intents.index("ask_contact")
    # Shown as soon as operation and zone are known, with up to 3 sample cards.
    cards = chat.turns[2][0]["cards"]
    assert 0 < len(cards) <= 3
    assert all(card["is_sample"] and card["link"].startswith("/ejemplo/") for card in cards)
    assert intents[-1] == "close"
    assert chat.state()["contact"] == "ana@example.com"


def test_over_budget_listings_are_flagged() -> None:
    chat = Chat(_config(_question("operation"), _question("budget"), _question("zone")))
    chat.say("Hola")
    chat.say("Quiero alquilar")
    chat.say("hasta 800 mil pesos")
    (cards_message, _) = chat.say("Palermo")

    flags = {card["id"]: card["over_budget"] for card in cards_message["cards"]}
    assert flags == {"palermo-honduras-mono": False, "palermo-guemes-2amb-alq": True}


def test_tone_changes_wording_but_not_the_sequence_of_intents() -> None:
    runs = {}
    for tone in Tone:
        chat = Chat(replace(DEFAULTS, tone=tone))
        for text in SCRIPT:
            chat.say(text)
        runs[tone] = (chat.intents(), [m["text"] for turn in chat.turns for m in turn])

    intents = {tuple(run[0]) for run in runs.values()}
    assert len(intents) == 1
    assert runs[Tone.WARM][1] != runs[Tone.FORMAL][1]
    assert runs[Tone.FORMAL][1][0].startswith("Buen día. Mi nombre es Sofía")


def test_after_closing_the_agent_does_not_restart_the_flow() -> None:
    chat = Chat()
    for text in SCRIPT:
        chat.say(text)

    chat.say("¿y cuándo me llaman?")

    assert chat.intents()[-1] == "after_close"


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"operation": "alquiler"}, "Alquiler"),
        ({"budget": {"amount": 900000, "currency": "ARS"}}, "Hasta $900.000"),
        ({"budget": {"amount": 120000, "currency": "USD"}}, "USD 120.000"),
        ({"mortgage_approved": True}, "Sí"),
    ],
)
def test_known_values_are_formatted_for_display(answers: dict, expected: str) -> None:
    rows = known_rows(DEFAULTS, {"answers": {**answers, "unknown_key": "x"}})

    values = [row.value for row in rows if row.value]
    assert values == [expected]
    assert [row.value for row in rows][-2:] == [None, None]
