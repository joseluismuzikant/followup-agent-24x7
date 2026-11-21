"""Property conditions in whole conversations (the real graph, the fake LLM): facts said in
passing, the options ordered what-fits-first, the one decisive question before a visit,
the requirement said plainly, and "nothing fits"."""

from collections.abc import Sequence
from uuid import UUID

from inmo24x7_api.properties.domain.conditions import (
    ConditionSettings,
    Guarantee,
    PropertyConditions,
)
from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.search import Listing
from lead_fakes import Chat, ListingSearch

CAUCION = frozenset({Guarantee.CAUCION})


class PolicySearch(ListingSearch):
    """Fixed listings and the agency's "Condiciones generales"."""

    def __init__(
        self, listings: Sequence[Listing], settings: ConditionSettings | None = None
    ) -> None:
        super().__init__(listings)
        self.settings = settings or ConditionSettings()

    def policy(self, tenant_id: UUID) -> ConditionSettings:
        return self.settings


def listing(
    slug: str,
    street: str,
    price: int,
    operation: Operation = Operation.RENT,
    **conditions,
) -> Listing:
    return Listing(
        id=f"00000000-0000-0000-0000-{slug:0>12}",
        title="2 ambientes",
        address=f"{street} 4800",
        operation=operation,
        zone="Palermo",
        price=price,
        currency=Currency.ARS if operation is Operation.RENT else Currency.USD,
        rooms=2,
        link=f"https://x.test/{street.lower()}",
        is_sample=False,
        conditions=PropertyConditions(**conditions),
    )


GORRITI = listing("1", "Gorriti", 800_000, garantias=CAUCION, contrato_minimo_meses=24)
HONDURAS = listing("2", "Honduras", 900_000)


def texts(messages: list[dict]) -> list[str]:
    return [message["text"] for message in messages if message["author"] == "agent"]


def card_addresses(chat: Chat) -> list[str]:
    cards = next(m["cards"] for turn in chat.turns for m in turn if m["cards"])
    return [card["address"] for card in cards]


def test_a_requirement_the_lead_cannot_meet_is_said_before_the_visit() -> None:
    chat = Chat(search=PolicySearch([GORRITI, HONDURAS]))
    chat.say("Hola")
    chat.say("Quiero alquilar por 1 mes")
    chat.say("Palermo")

    # The 24-month one does not fit a 1-month stay: shown, but after the one with no data.
    assert card_addresses(chat) == ["Honduras 4800", "Gorriti 4800"]
    assert chat.state()["answers"]["plazo_meses"] == 1
    assert not any("no cumpl" in text.lower() for text in texts(chat.turns[-1]))

    asked = chat.say("Me interesa la de Gorriti")
    assert chat.asked()[-1] == "garantia"  # the one question this property needs
    assert not asked[0]["slots"]

    check = chat.say("No tengo garantía")
    assert check[0]["text"] == (
        "Antes de coordinar: esta propiedad pide seguro de caución. ¿Podrías cumplir con eso?"
    )
    state = chat.state()
    assert state["answers"]["garantia"] == "ninguna"
    assert state["asked_key"] == "puede_cumplir"

    alternative = chat.say("no puedo")
    assert chat.intents()[-1] == "offer_fitting"
    assert "Honduras 4800" in alternative[0]["text"]
    state = chat.state()
    assert [event["kind"] for event in state["condition_events"]] == ["mismatch", "visit_avoided"]
    assert state["chosen_property_ids"] == [GORRITI.id]
    assert state["property_matches"][GORRITI.id]["status"] == "no_cumple"
    assert state["property_matches"][HONDURAS.id]["status"] == "sin_datos"
    assert not state.get("visit_offer")


def test_a_lead_who_can_meet_it_gets_the_visit_times_and_it_is_noted() -> None:
    chat = Chat(search=PolicySearch([GORRITI]))
    for text in ["Hola", "Quiero alquilar por 2 años con garantía propietaria", "Palermo"]:
        chat.say(text)
    chat.say("Me interesa la de Gorriti")

    assert chat.intents()[-1] == "requirement_check"
    slots = chat.say("sí, consigo el seguro")

    assert slots[0]["slots"]
    state = chat.state()
    assert state["answers"]["acepta_requisitos"] == ["garantia"]
    assert state["property_matches"][GORRITI.id]["status"] == "cumple"
    assert state["property_matches"][GORRITI.id]["accepted"] == ["seguro de caución"]


def test_with_the_switch_off_the_visit_goes_on_and_only_the_team_sees_it() -> None:
    settings = ConditionSettings(warn_before_visit=False)
    chat = Chat(search=PolicySearch([GORRITI], settings))
    for text in ["Hola", "Quiero alquilar por 1 mes sin garantía", "Palermo"]:
        chat.say(text)

    offered = chat.say("Me interesa la de Gorriti")

    assert offered[0]["slots"]
    assert chat.state()["property_matches"][GORRITI.id]["status"] == "no_cumple"


def test_a_pet_said_in_passing_is_captured_and_orders_the_options() -> None:
    no_pets = listing("3", "Thames", 500_000, mascotas=False)
    pets = listing("4", "Malabia", 700_000, mascotas=True)
    chat = Chat(search=PolicySearch([no_pets, pets]))

    chat.say("Hola, quiero alquilar y tengo un perro")
    chat.say("Palermo")

    assert chat.state()["answers"]["tiene_mascota"] is True
    assert card_addresses(chat) == ["Malabia 4800", "Thames 4800"]
    presented = next(t for turn in chat.turns for t in texts(turn) if "Mirá estas" in t)
    assert presented.endswith("La primera acepta mascotas.")


def test_a_sale_with_credit_puts_the_apt_one_first() -> None:
    apt = listing("5", "Cabildo", 190_000, Operation.SALE, apto_credito=True)
    not_apt = listing("6", "Juramento", 150_000, Operation.SALE, apto_credito=False)
    chat = Chat(search=PolicySearch([not_apt, apt]))

    chat.say("Hola, quiero comprar con crédito hipotecario")
    chat.say("Palermo")

    assert chat.state()["answers"]["necesita_credito"] is True
    # Cheaper first by budget order, but the apt one fits: it goes first.
    assert card_addresses(chat) == ["Cabildo 4800", "Juramento 4800"]
    presented = next(t for turn in chat.turns for t in texts(turn) if "Mirá estas" in t)
    assert presented.endswith("La primera es apta crédito.")
    # Credit is a feature: never a "no cumple", only a note for the team.
    assert chat.state()["property_matches"][not_apt.id]["status"] == "cumple"
    assert chat.state()["property_matches"][not_apt.id]["notes"] == ["no es apta crédito"]


def test_the_credit_question_is_asked_before_visiting_a_sale_that_says_so() -> None:
    apt = listing("5", "Cabildo", 190_000, Operation.SALE, apto_credito=True)
    chat = Chat(search=PolicySearch([apt]))
    for text in ["Hola", "Quiero comprar", "Palermo"]:
        chat.say(text)

    chat.say("Me interesa la de Cabildo")
    assert chat.asked()[-1] == "necesita_credito"
    slots = chat.say("sí")

    assert slots[0]["slots"]
    assert chat.state()["answers"]["necesita_credito"] is True


def test_a_property_without_conditions_never_blocks_anything() -> None:
    chat = Chat(search=PolicySearch([HONDURAS]))
    for text in ["Hola", "Quiero alquilar por 1 mes sin garantía", "Palermo"]:
        chat.say(text)

    offered = chat.say("Me interesa la de Honduras")

    assert offered[0]["slots"]
    assert chat.state()["property_matches"][HONDURAS.id]["status"] == "sin_datos"


def test_a_disabled_active_question_is_not_asked() -> None:
    from dataclasses import replace

    from lead_fakes import DEFAULTS

    config = replace(
        DEFAULTS,
        qualification_questions=tuple(
            replace(q, enabled=False) if q.key == "garantia" else q
            for q in DEFAULTS.qualification_questions
        ),
    )
    chat = Chat(config, search=PolicySearch([GORRITI]))
    for text in ["Hola", "Quiero alquilar por 3 años", "Palermo"]:
        chat.say(text)

    offered = chat.say("Me interesa la de Gorriti")

    assert "garantia" not in chat.asked()
    assert offered[0]["slots"]


def test_when_nothing_fits_she_asks_once_about_the_requirement() -> None:
    long_one = listing("7", "Gurruchaga", 600_000, contrato_minimo_meses=24)
    longer = listing("8", "Armenia", 650_000, contrato_minimo_meses=36)
    chat = Chat(search=PolicySearch([long_one, longer]))
    chat.say("Hola")
    chat.say("Quiero alquilar por 6 meses")
    presented = chat.say("Palermo")

    assert presented[-1]["text"] == (
        "Por ahora las opciones que tenemos piden contrato de 2 años. ¿Te interesaría verlas igual?"
    )
    assert chat.state()["asked_key"] == "ver_alternativas"

    again = chat.say("sí")
    assert again[0]["cards"]
    state = chat.state()
    assert state["answers"]["acepta_requisitos"] == ["contrato_minimo"]
    assert state["property_matches"][long_one.id]["status"] == "cumple"


def test_when_nothing_fits_and_the_lead_says_no_she_thanks_and_it_is_marked() -> None:
    long_one = listing("7", "Gurruchaga", 600_000, contrato_minimo_meses=24)
    chat = Chat(search=PolicySearch([long_one]))
    for text in ["Hola", "Quiero alquilar por 6 meses", "Palermo"]:
        chat.say(text)

    closing = chat.say("no, gracias")

    assert "no tengo opciones con esas condiciones" in closing[0]["text"]
    assert [event["kind"] for event in chat.state()["condition_events"]] == ["no_fit"]


def test_no_relax_question_when_the_switch_is_off() -> None:
    long_one = listing("7", "Gurruchaga", 600_000, contrato_minimo_meses=24)
    chat = Chat(search=PolicySearch([long_one], ConditionSettings(offer_alternatives=False)))
    for text in ["Hola", "Quiero alquilar por 6 meses"]:
        chat.say(text)

    chat.say("Palermo")

    assert "ask_relax" not in chat.intents()


def test_never_asks_income() -> None:
    chat = Chat(search=PolicySearch([GORRITI]))
    for text in ["Hola", "Quiero alquilar", "Palermo", "Me interesa la de Gorriti"]:
        chat.say(text)

    every_text = " ".join(t for turn in chat.turns for t in texts(turn)).lower()
    assert "ingreso" not in every_text and "sueldo de" not in every_text


def test_a_tapped_card_goes_on_with_its_decisive_question() -> None:
    chat = Chat(search=PolicySearch([GORRITI, HONDURAS]))
    for text in ["Hola", "Quiero alquilar", "Palermo"]:
        chat.say(text)

    # The simulator sends the card's title and its id: the id decides, not the text.
    asked = chat.say("2 ambientes", choice_id=GORRITI.id)

    assert chat.asked()[-1] == "garantia"
    assert not asked[0]["slots"]
    assert chat.state()["pending_card"] == GORRITI.id
