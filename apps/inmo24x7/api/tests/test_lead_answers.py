"""Answering what the lead asks (ANSWER_QUESTION) and changing a search answer (1.3, 1.4):
whole conversations through the real graph with the fake model."""

from collections.abc import Sequence
from uuid import UUID

from followup_core.conversation.domain.llm import ReplyIntent
from inmo24x7_api.leads.safe_texts import DEFERRED_ANSWER
from inmo24x7_api.properties.domain.conditions import (
    ConditionSettings,
    Guarantee,
    PropertyConditions,
)
from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.search import Listing
from lead_fakes import Chat, ListingSearch


class PolicySearch(ListingSearch):
    def __init__(self, listings: Sequence[Listing]) -> None:
        super().__init__(listings)

    def policy(self, tenant_id: UUID) -> ConditionSettings:
        return ConditionSettings()


def listing(slug: str, street: str, price: int, zone: str = "Palermo", **conditions) -> Listing:
    return Listing(
        id=f"00000000-0000-0000-0000-{slug:0>12}",
        title="2 ambientes",
        address=f"{street} 4800",
        operation=Operation.RENT,
        zone=zone,
        price=price,
        currency=Currency.ARS,
        rooms=2,
        link=f"https://x.test/{street.lower()}",
        is_sample=False,
        conditions=PropertyConditions(**conditions),
    )


THAMES = listing("1", "Thames", 900_000, mascotas=False)
MALABIA = listing("2", "Malabia", 700_000, mascotas=True)
GORRITI = listing("3", "Gorriti", 800_000, garantias=frozenset({Guarantee.CAUCION}))
ACOYTE = listing("4", "Acoyte", 650_000, zone="Caballito")


def _chat(*listings: Listing) -> Chat:
    chat = Chat(search=PolicySearch(listings))
    for text in ["Hola", "Quiero alquilar", "Palermo"]:
        chat.say(text)
    return chat


def _cards(chat: Chat) -> list[dict]:
    return next(m["cards"] for turn in reversed(chat.turns) for m in turn if m["cards"])


def _texts(messages: list[dict]) -> list[str]:
    return [m["text"] for m in messages if m["author"] == "agent"]


def test_a_question_about_one_option_gets_a_grounded_answer_then_the_next_step() -> None:
    chat = _chat(THAMES, MALABIA)
    cards = _cards(chat)
    position = ["primera", "segunda"][[c["id"] for c in cards].index(MALABIA.id)]

    messages = chat.say(f"¿acepta mascotas la {position}?")

    answer, step = _texts(messages)
    assert answer == f"Sí, la {position} acepta mascotas."
    # Then the planner's own step, in its own message (the fake reads "la segunda" as a pick
    # too, so it is that property's visit times).
    assert chat.intents()[-2:] == [
        ReplyIntent.ANSWER_QUESTION.value,
        ReplyIntent.OFFER_SLOTS.value,
    ]
    assert "?" in step and "?" not in answer
    state = chat.state()
    assert (state["answers_given"], state["answers_deferred"]) == (1, 0)
    # The answer was made only from the shown options, sent as data.
    request = chat.llm.replies[-2]
    assert [o["direccion"] for o in request.data["opciones"]] == [c["address"] for c in cards]
    assert request.lead_message == f"¿acepta mascotas la {position}?"


def test_a_comparison_is_answered_from_the_data() -> None:
    chat = _chat(THAMES, MALABIA)

    answer, _ = _texts(chat.say("¿cuál es la más barata?"))

    assert answer.startswith("La más barata es la ")
    assert "$700.000" in answer.replace(" ", "")


def test_what_is_not_in_the_data_is_checked_with_the_team() -> None:
    chat = _chat(THAMES, MALABIA)

    answer, _ = _texts(chat.say("¿tiene cochera?"))

    assert answer == DEFERRED_ANSWER
    assert chat.state()["answers_deferred"] == 1


def test_a_changed_zone_searches_again_without_telling_a_requirement_twice() -> None:
    chat = Chat(search=PolicySearch([GORRITI, ACOYTE]))
    for text in ["Hola", "Quiero alquilar sin garantía", "Palermo"]:
        chat.say(text)
    chat.say("Me interesa la de Gorriti")
    assert chat.intents()[-1] == ReplyIntent.REQUIREMENT_CHECK.value
    told = chat.state()["requirements_asked"]

    messages = chat.say("¿y en Caballito?")

    assert [card["id"] for card in _cards(chat)] == [ACOYTE.id]
    assert ReplyIntent.PRESENT_OPTIONS.value in chat.intents()[-2:]
    state = chat.state()
    assert state["answers"]["zone"] == "Caballito"
    assert state["requirements_asked"] == told
    assert state["requirement_check"] is None and state["pending_card"] is None
    assert GORRITI.id in state["shown_property_ids"] and ACOYTE.id in state["shown_property_ids"]
    assert not any("caución" in text for text in _texts(messages))


def test_an_answer_and_a_pick_in_one_message() -> None:
    chat = Chat(search=PolicySearch([GORRITI, THAMES]))
    for text in ["Hola", "Quiero alquilar", "Palermo"]:
        chat.say(text)
    cards = _cards(chat)
    position = ["primera", "segunda"][[c["id"] for c in cards].index(GORRITI.id)]

    messages = chat.say(f"la {position}, ¿tiene balcón?")

    answer, gate = _texts(messages)
    assert answer == DEFERRED_ANSWER
    # Then that property's gate: the one question it needs (its guarantee).
    assert chat.intents()[-2:] == [ReplyIntent.ANSWER_QUESTION.value, ReplyIntent.ASK.value]
    assert chat.asked()[-1] == "garantia"
    assert chat.state()["pending_card"] == GORRITI.id


def test_a_tapped_button_never_counts_as_a_question() -> None:
    chat = _chat(THAMES, MALABIA)
    card = _cards(chat)[0]

    chat.say("¿tiene cochera?", choice_id=card["id"])

    assert ReplyIntent.ANSWER_QUESTION.value not in chat.intents()


def test_after_a_human_hand_off_nothing_is_answered() -> None:
    chat = _chat(THAMES, MALABIA)
    chat.say("quiero hablar con una persona")
    calls = chat.llm.calls

    chat.say("¿acepta mascotas la primera?")

    assert ReplyIntent.ANSWER_QUESTION.value not in chat.intents()
    assert chat.llm.calls == calls + 1  # only the after-hand-off reply, worded once
