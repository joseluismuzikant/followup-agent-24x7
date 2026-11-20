"""The website button's first message ("Consultar por WhatsApp", widget.js): the property it
names is already chosen. The graph with the fake model; no database."""

from uuid import UUID, uuid4

from followup_core.conversation.domain.llm import ReplyIntent
from inmo24x7_api.properties.domain.conditions import Guarantee, PropertyConditions
from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.reference import (
    WEB_GENERIC_TEXT,
    read_web_reference,
    web_property_text,
)
from inmo24x7_api.properties.domain.search import Listing
from lead_fakes import Chat, ListingSearch

GORRITI = Listing(
    id=str(uuid4()),
    title="2 ambientes luminoso",
    address="Gorriti 4800",
    operation=Operation.RENT,
    zone="Palermo",
    price=850_000,
    currency=Currency.ARS,
    rooms=2,
    link="https://www.inmosur.com.ar/propiedades/gorriti-4800",
    is_sample=False,
)
CABILDO = Listing(
    id=str(uuid4()),
    title="3 ambientes con balcón",
    address="Cabildo 2100",
    operation=Operation.RENT,
    zone="Belgrano",
    price=1_200_000,
    currency=Currency.ARS,
    rooms=3,
    link="https://www.inmosur.com.ar/propiedades/cabildo-2100",
    is_sample=False,
    conditions=PropertyConditions(garantias=frozenset({Guarantee.CAUCION})),
)


def _chat() -> Chat:
    return Chat(search=ListingSearch([GORRITI, CABILDO]))


# --- Reading the text ------------------------------------------------------------------------


def test_the_button_text_names_the_property_by_id_code_or_link() -> None:
    by_id = read_web_reference(web_property_text("2 ambientes", GORRITI.id))
    by_code = read_web_reference("Hola, me interesa la propiedad «Casa» (ref. TKO-1234)")
    by_link = read_web_reference(web_property_text("Casa", GORRITI.link + "/"))

    assert by_id is not None and by_id.from_button
    assert by_id.reference.property_id == UUID(GORRITI.id)
    assert by_id.title == "2 ambientes"
    assert by_code is not None and by_code.reference.code == "TKO-1234"
    assert by_link is not None and by_link.reference.links == (GORRITI.link + "/",)


def test_a_pasted_link_or_the_generic_text_and_nothing_else() -> None:
    pasted = read_web_reference(f"Hola! vi esto {GORRITI.link}, sigue disponible?")
    generic = read_web_reference(WEB_GENERIC_TEXT)

    assert pasted is not None and not pasted.from_button
    assert pasted.reference.links == (GORRITI.link,)
    assert generic is not None and generic.from_button and generic.reference.is_empty
    assert read_web_reference("Hola, busco alquilar en Palermo") is None
    assert read_web_reference("me interesa la planta baja") is None


# --- The conversation ------------------------------------------------------------------------


def test_the_named_property_is_chosen_and_goes_to_its_visit_times() -> None:
    chat = _chat()

    greeting, slots = chat.say(web_property_text(GORRITI.title, GORRITI.link))

    assert chat.intents() == [ReplyIntent.GREET.value, ReplyIntent.OFFER_SLOTS.value]
    # Sofía confirms the property; she does not present other options.
    assert "2 ambientes luminoso · Gorriti 4800" in greeting["text"]
    assert greeting["cards"] is None
    assert slots["slots"] and "Gorriti 4800" in slots["text"]
    state = chat.state()
    assert state["chosen_property_ids"] == [GORRITI.id]
    assert state["visit_offer"]["property_id"] == GORRITI.id
    assert state["lead_source"] == "web_button"
    # Its operation and zone are the property's: never asked.
    assert state["answers"]["operation"] == "alquiler" and state["answers"]["zone"] == "Palermo"
    assert "search_properties" not in chat.tool_calls


def test_it_asks_only_what_the_named_property_still_needs() -> None:
    chat = _chat()

    chat.say(web_property_text(CABILDO.title, CABILDO.id))

    assert chat.intents() == [ReplyIntent.GREET.value, ReplyIntent.ASK.value]
    assert chat.asked() == ["garantia"]
    assert chat.state()["pending_card"] == CABILDO.id

    chat.say("Tengo seguro de caución")

    assert chat.intents()[-1] == ReplyIntent.OFFER_SLOTS.value
    assert chat.state()["visit_offer"]["property_id"] == CABILDO.id


def test_an_unknown_reference_is_a_normal_conversation_from_the_web() -> None:
    chat = _chat()

    chat.say(web_property_text("Casa", "TKO-9999"))

    assert ReplyIntent.OFFER_SLOTS.value not in chat.intents()
    state = chat.state()
    assert state["lead_source"] == "web_button"
    assert not state.get("chosen_property_ids")


def test_only_the_first_message_counts() -> None:
    chat = _chat()
    chat.say("Hola, busco alquilar")

    chat.say(web_property_text(GORRITI.title, GORRITI.link))

    assert "find_referenced_property" not in chat.tool_calls
    assert not chat.state().get("lead_source")
