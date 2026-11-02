"""The inmo24x7 qualification graph, run through the real LangGraph runtime with the fake LLM
and an in-memory checkpointer. The flow must not depend on the model."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from followup_core.conversation.domain.llm import ReplyIntent
from followup_core.tenancy.domain.agent_config import (
    AgentConfig,
    QualificationQuestion,
    QuestionKind,
    Tone,
)
from inmo24x7_api.leads.display import known_rows, looking_for
from inmo24x7_api.leads.graph import plan_turn
from inmo24x7_api.leads.tools import DECLARED, HAND_OFF_EVENT, lead_handlers, lead_tools
from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.search import Listing
from lead_fakes import DEFAULTS, Chat, ListingSearch


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
    # Contact known, nothing picked yet: the agent invites a visit once before handing off.
    assert intents[-1] == "offer_visit"
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


def test_declining_the_visit_hands_off_and_the_flow_never_restarts() -> None:
    chat = Chat()
    for text in SCRIPT:
        chat.say(text)

    handed = chat.say("no, gracias")
    chat.say("¿y cuándo me llaman?")

    assert [m["author"] for m in handed] == ["agent", "system"]
    assert handed[1]["text"] == HAND_OFF_EVENT
    assert chat.state()["hand_off_reason"] == "qualified"
    assert chat.intents()[-1] == "after_hand_off"


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


# --- Day 4: visits and hand-off ---------------------------------------------------------

DONE_WHEN = [
    "Hola",
    "Quiero alquilar",
    "Palermo",
    "Me interesa la primera",
]


def _pick_first_slot(chat: Chat) -> list[dict]:
    (offer,) = chat.turns[-1]
    return chat.say(offer["slots"][0]["label"])


def test_done_when_conversation_proposes_slots_and_hands_off() -> None:
    chat = Chat()
    for text in DONE_WHEN[:3]:
        chat.say(text)
    cards = chat.turns[2][0]["cards"]

    (offer,) = chat.say("Me interesa la primera")
    assert [slot["label"] for slot in offer["slots"]] == [
        "martes 3/11, 13:00",
        "martes 3/11, 13:30",
    ]
    assert cards[0]["title"] in offer["text"]

    chosen = _pick_first_slot(chat)
    assert [m["text"] for m in chosen][0].startswith("¡Listo! Te anoté para el martes 3/11, 13:00")
    assert chat.intents()[-2:] == ["slot_chosen", "ask_name"]

    chat.say("Me llamo Ana Pérez")
    assert chat.intents()[-1] == "ask_contact"
    final = chat.say("11 5555-1234")

    assert [(m["author"], m["text"]) for m in final][-1] == ("system", HAND_OFF_EVENT)
    state = chat.state()
    assert (state["visitor_name"], state["contact"]) == ("Ana Pérez", "+54 9 11 5555-1234")
    assert state["visit"]["property_id"] == cards[0]["id"]
    assert state["visit"]["starts_at"] == "2026-11-03T13:00:00-03:00"
    assert state["hand_off_reason"] == "visit"
    assert looking_for(state["answers"]) == "Alquiler · Palermo"


def test_after_the_hand_off_the_agent_never_proposes_a_visit_again() -> None:
    chat = Chat()
    for text in DONE_WHEN:
        chat.say(text)
    _pick_first_slot(chat)
    chat.say("Me llamo Ana Pérez")
    chat.say("ana@example.com")

    for text in ["Me interesa la segunda", "¿Tienen algo en Belgrano?", "la 1"]:
        (reply,) = chat.say(text)
        assert reply["slots"] is None and reply["cards"] is None
    assert chat.intents()[-3:] == ["after_hand_off"] * 3


@pytest.mark.parametrize("step", range(len(DONE_WHEN) + 2))
def test_asking_for_a_person_hands_off_at_any_step(step: int) -> None:
    chat = Chat()
    for text in DONE_WHEN[:step]:
        chat.say(text)
    if step > len(DONE_WHEN):
        _pick_first_slot(chat)

    messages = chat.say("Prefiero hablar con una persona")

    assert messages[-1] == {
        "text": HAND_OFF_EVENT,
        "author": "system",
        "cards": None,
        "slots": None,
    }
    assert chat.state()["hand_off_reason"] == "human"
    (later,) = chat.say("Me interesa la primera")
    assert later["slots"] is None
    assert chat.intents()[-1] == "after_hand_off"


def test_asking_for_a_person_after_a_visit_hand_off_marks_the_request() -> None:
    chat = Chat()
    for text in DONE_WHEN:
        chat.say(text)
    _pick_first_slot(chat)
    chat.say("Me llamo Ana Pérez")
    chat.say("ana@example.com")

    chat.say("Quiero hablar con alguien ahora")

    assert chat.state()["hand_off_reason"] == "human"
    assert chat.intents()[-1] == "after_hand_off"


def test_out_of_hours_the_agent_still_proposes_slots_and_says_the_team_confirms() -> None:
    saturday = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
    chat = Chat(now=saturday)
    for text in DONE_WHEN:
        chat.say(text)

    (offer,) = chat.turns[-1]
    assert [slot["label"] for slot in offer["slots"]] == ["lunes 9/11, 09:00", "lunes 9/11, 09:30"]
    assert "te lo confirman apenas vuelvan" in offer["text"]


def test_without_team_hours_the_visit_goes_to_a_person() -> None:
    chat = Chat(team_hours=())
    for text in DONE_WHEN:
        chat.say(text)

    assert chat.turns[-1][-1]["author"] == "system"
    assert chat.state()["hand_off_reason"] == "qualified"


def test_an_invalid_contact_is_not_saved_and_asked_again() -> None:
    chat = Chat()
    for text in SCRIPT[:-1]:
        chat.say(text)

    chat.say("5555-1234")  # no area code: not a valid Argentine number

    assert chat.intents()[-1] == "invalid_contact"
    assert chat.state().get("contact") is None
    chat.say("011 15 5555-1234")
    assert chat.state()["contact"] == "+54 9 11 5555-1234"


OWN = [
    Listing(
        id="7d1e6c1e-1111-4a8e-9b1a-000000000001",
        title="2 ambientes luminoso",
        address="Gorriti 4800",
        operation=Operation.RENT,
        zone="Palermo",
        price=850_000,
        currency=Currency.ARS,
        rooms=2,
        link="https://www.inmobiliariasur.example/propiedades/gorriti-4800",
        is_sample=False,
    ),
    Listing(
        id="7d1e6c1e-1111-4a8e-9b1a-000000000002",
        title="2 ambientes reciclado",
        address="Thames 1500",
        operation=Operation.RENT,
        zone="Palermo",
        price=900_000,
        currency=Currency.ARS,
        rooms=2,
        link="https://www.inmobiliariasur.example/propiedades/thames-1500",
        is_sample=False,
    ),
]


def test_cards_only_carry_the_links_of_the_search_results() -> None:
    chat = Chat(search=ListingSearch(OWN))
    for text in DONE_WHEN:
        chat.say(text)

    links = {listing.link for listing in OWN}
    cards = [card for m in chat.all_messages() for card in m["cards"] or []]
    assert cards and {card["link"] for card in cards} <= links
    assert not any(card["is_sample"] for card in cards)
    # "la de Thames" picks by address.
    chat2 = Chat(search=ListingSearch(OWN))
    for text in DONE_WHEN[:3]:
        chat2.say(text)
    chat2.say("Me gusta la de Thames")
    assert chat2.state()["visit_offer"]["property_id"] == OWN[1].id


def test_every_declared_tool_has_a_handler_and_is_reached_from_the_graph() -> None:
    search = ListingSearch()
    assert set(DECLARED) == set(lead_handlers(search)) == lead_tools(search).names

    reached: set[str] = set()
    visit = Chat()
    for text in DONE_WHEN:
        visit.say(text)
    _pick_first_slot(visit)
    visit.say("Me llamo Ana Pérez")
    visit.say("ana@example.com")
    reached |= set(visit.tool_calls)

    assert reached == set(DECLARED)


def test_plan_never_asks_for_personal_data_before_showing_options() -> None:
    questions = [q for q in DEFAULTS.qualification_questions if q.enabled]
    state = {"inbound": "", "outbox": [], "turns": 3, "answers": {"operation": "alquiler"}}

    steps = plan_turn(state, questions)  # type: ignore[arg-type]

    assert [step.intent for step in steps] == [ReplyIntent.ASK]
    assert steps[0].question is not None and steps[0].question.key == "zone"
