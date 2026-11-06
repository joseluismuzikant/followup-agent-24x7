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

    # Renting: the mortgage question is skipped.
    assert chat.asked() == ["operation", "zone", "budget", "rooms"]
    for request in chat.llm.replies:
        if request.question is not None:
            assert request.intent in (ReplyIntent.GREET, ReplyIntent.ASK)
    # Only one message per turn carries a question.
    for messages in chat.turns:
        assert sum(text.count("?") for text in (m["text"] for m in messages)) <= 1


def test_the_mortgage_question_is_only_asked_when_buying() -> None:
    chat = Chat()
    for text in ["Hola", "Quiero comprar", "Palermo", "hasta 150 mil dólares", "no", "2"]:
        chat.say(text)

    assert chat.asked() == ["operation", "zone", "budget", "mortgage_approved", "rooms"]
    assert chat.state()["answers"]["mortgage_approved"] is False


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
        "martes 3/11, 16:00",
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
    cards = [card["id"] for card in chat.turns[2][0]["cards"]]

    for text in ["¿Tienen algo en Belgrano?", f"Me gusta la de {cards[1]}"]:
        (reply,) = chat.say(text)
        assert reply["slots"] is None and reply["cards"] is None
        assert chat.intents()[-1] == "after_hand_off"
    assert chat.state()["visit_offer"]["property_id"] == cards[0]


def test_another_slot_replaces_the_visit_before_and_after_the_hand_off() -> None:
    chat = Chat()
    for text in DONE_WHEN:
        chat.say(text)
    (offer,) = chat.turns[-1]
    first, second = offer["slots"]
    chat.say(first["label"])
    assert chat.state()["visit"]["label"] == first["label"]

    # Before the hand-off: a different slot replaces it.
    chat.say(second["label"])
    assert chat.state()["visit"]["label"] == second["label"]
    assert chat.intents()[-2:] == ["slot_chosen", "ask_name"]

    chat.say("Me llamo Ana Pérez")
    chat.say("ana@example.com")
    assert chat.state()["hand_off_reason"] == "visit"

    # After the hand-off the reply buttons still work: a tapped slot changes the time.
    chat.say(first["label"], choice_id=first["id"])
    assert chat.state()["visit"]["label"] == first["label"]
    assert chat.intents()[-1] == "slot_chosen"
    # Tapping the same slot again changes nothing.
    chat.say(first["label"], choice_id=first["id"])
    assert chat.intents()[-1] == "after_hand_off"


def test_another_property_gets_its_own_slots_and_then_replaces_the_visit() -> None:
    chat = Chat()
    for text in DONE_WHEN:
        chat.say(text)
    cards = chat.turns[2][0]["cards"]
    _pick_first_slot(chat)

    (offer,) = chat.say("Mejor la segunda propiedad", choice_id=cards[1]["id"])
    assert offer["slots"] and chat.intents()[-1] == "offer_slots"
    chat.say(offer["slots"][1]["label"], choice_id=offer["slots"][1]["id"])

    visit = chat.state()["visit"]
    assert (visit["property_id"], visit["label"]) == (cards[1]["id"], offer["slots"][1]["label"])


def test_a_tapped_choice_wins_over_the_text_and_must_have_been_offered() -> None:
    chat = Chat()
    for text in DONE_WHEN[:3]:
        chat.say(text)
    cards = chat.turns[2][0]["cards"]

    chat.say("la primera", choice_id="not-offered")
    assert chat.state()["visit_offer"]["property_id"] == cards[0]["id"]
    (offer,) = chat.turns[-1]
    chat.say("la primera", choice_id=offer["slots"][1]["id"])
    assert chat.state()["visit"]["label"] == offer["slots"][1]["label"]


def test_a_contact_known_by_the_channel_is_never_asked_for() -> None:
    chat = Chat(visitor_contact="+54 9 11 5555-0188")
    for text in [*DONE_WHEN]:
        chat.say(text)
    _pick_first_slot(chat)
    chat.say("Me llamo Ana Pérez")

    assert "ask_contact" not in chat.intents()
    assert chat.state()["contact"] == "+54 9 11 5555-0188"
    assert chat.state()["hand_off_reason"] == "visit"


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
    assert [slot["label"] for slot in offer["slots"]] == ["lunes 9/11, 09:00", "lunes 9/11, 12:00"]
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


def test_each_reply_only_gets_the_facts_of_its_own_step() -> None:
    chat = Chat(visitor_contact="+54 9 11 5555-0188")
    for text in DONE_WHEN:
        chat.say(text)
    (offer,) = chat.turns[-1]
    chat.say("Me llamo Ana Pérez")
    slot = offer["slots"][0]
    chat.say(slot["label"], choice_id=slot["id"])

    # The hand-off is said in the slot's own message: no second reply is composed.
    chosen = chat.llm.replies[-1]
    assert chosen.intent is ReplyIntent.SLOT_CHOSEN
    assert set(chosen.facts) == {"visitor_name", "slot", "hand_off"}
    assert [m["author"] for m in chat.turns[-1]] == ["agent", "system"]
    # The greeting's facts stay with the greeting.
    assert all("looking_for" not in r.facts for r in chat.llm.replies[1:])


def _rent(slug: str, address: str, rooms: int, price: int) -> Listing:
    return Listing(
        id=slug,
        title=f"{rooms} ambientes",
        address=address,
        operation=Operation.RENT,
        zone="Palermo",
        price=price,
        currency=Currency.ARS,
        rooms=rooms,
        link=f"https://www.inmobiliariasur.example/propiedades/{slug}",
        is_sample=False,
    )


# The production conversation of 7 November 2026, with one more 2-room listing so the exact
# matches fill every slot.
PALERMO = [
    _rent("guatemala-5200", "Guatemala 5200", 3, 1_250_000),
    _rent("gorriti-4800", "Gorriti 4800", 2, 850_000),
    _rent("thames-1500", "Thames 1500", 2, 900_000),
    _rent("soler-4500", "Soler 4500", 2, 950_000),
]


def test_the_production_transcript_greets_without_asking_and_closes_once() -> None:
    saturday = datetime(2026, 11, 7, 14, 0, tzinfo=UTC)
    chat = Chat(search=ListingSearch(PALERMO), now=saturday, visitor_contact="+5491151060793")

    greeting, options, budget = chat.say("Hola, busco un 2 ambientes para alquilar en Palermo")
    # (1) The greeting acknowledges the search and asks nothing; only the next message asks.
    assert greeting["text"] == (
        "¡Hola! Soy Sofía, de Inmobiliaria Sur. Buenísimo, te busco opciones de 2 ambientes "
        "en alquiler en Palermo."
    )
    assert "?" not in greeting["text"] and "?" in budget["text"]
    # (2) Exact room matches fill the slots: the 3-room listing is not shown.
    assert [card["rooms"] for card in options["cards"]] == [2, 2, 2]
    assert "guatemala-5200" not in {card["id"] for card in options["cards"]}

    chat.say("hasta 900 mil")
    chat.say("Jose Luis")
    assert chat.intents()[-1] == "offer_visit"
    (offer,) = chat.say("la de gorriti me interesa")
    slot = offer["slots"][0]
    assert slot["label"] == "lunes 9/11, 09:00"

    # (3) The pick is one lead-facing message plus the hand-off system event.
    picked = chat.say(slot["short_label"], choice_id=slot["id"])
    assert [m["author"] for m in picked] == ["agent", "system"]
    assert picked[0]["text"] == (
        "¡Listo, Jose Luis! Te anoté para el lunes 9/11, 09:00. Una persona del equipo te lo "
        "confirma y sigue con tu consulta muy pronto."
    )
    assert picked[1]["text"] == HAND_OFF_EVENT
    assert chat.tool_calls.count("hand_off") == 1
    state = chat.state()
    assert state["hand_off_reason"] == "visit"
    assert state["visit"]["property_id"] == "gorriti-4800"
