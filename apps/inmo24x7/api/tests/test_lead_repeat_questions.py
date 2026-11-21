"""A question already answered is never asked again (the real graph, the fake LLM).

The real conversation: the lead chose "2 ambientes reciclado" on Thames, answered the
minimum-contract question, Sofía told them the requirement, the lead said "si dale", and
Sofía asked the same requirement again. The model had read "si dale" as picking that card
again (its id was still among the offered choices)."""

from dataclasses import replace

from followup_core.conversation.domain.llm import Extraction, ExtractionRequest
from inmo24x7_api.leads.conditions import PUEDE_CUMPLIR
from inmo24x7_api.properties.domain.conditions import Guarantee
from lead_fakes import Chat, RecordingLlm
from test_lead_conditions_graph import HONDURAS, PolicySearch, listing

THAMES = listing(
    "15",
    "Thames",
    750_000,
    garantias=frozenset({Guarantee.CAUCION, Guarantee.RECIBO_DE_SUELDO}),
    contrato_minimo_meses=6,
)


class MisreadingModel(RecordingLlm):
    """Reads the given replies as picking `card_id` again, as the real model did; with
    `reads_yes_no=False` it also misses the yes / no itself."""

    def __init__(self, card_id: str, replies: set[str], *, reads_yes_no: bool = True) -> None:
        super().__init__()
        self.card_id = card_id
        self.misread = replies
        self.reads_yes_no = reads_yes_no

    def extract(self, request: ExtractionRequest) -> Extraction:
        result = super().extract(request)
        if request.latest not in self.misread:
            return result
        values = dict(result.values)
        if not self.reads_yes_no:
            values.pop(PUEDE_CUMPLIR, None)
        return replace(result, choice_id=self.card_id, values=values)


def up_to_the_requirement(chat: Chat) -> list[dict]:
    for text in ["Hola", "Quiero alquilar con garantía propietaria", "Palermo"]:
        chat.say(text)
    asked = chat.say("Me interesa la de Thames")
    assert chat.asked()[-1] == "plazo_meses"  # the minimum contract
    assert not asked[0]["slots"]
    check = chat.say("6 meses")
    assert chat.intents()[-1] == "requirement_check"
    assert "pide seguro de caución" in check[0]["text"]
    return check


def requirement_questions(chat: Chat) -> list[str]:
    return [
        intent
        for intent in chat.intents()
        if intent in ("requirement_check", "requirement_confirm")
    ]


def test_si_dale_read_as_a_pick_of_the_same_card_goes_on_to_the_visit_times() -> None:
    llm = MisreadingModel(THAMES.id, {"si dale"})
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]), llm=llm)
    up_to_the_requirement(chat)

    slots = chat.say("si dale")

    assert slots[0]["slots"], slots
    assert requirement_questions(chat) == ["requirement_check"]
    state = chat.state()
    assert state["answers"]["acepta_requisitos"] == ["garantia"]
    assert state["visit_offer"]["property_id"] == THAMES.id
    assert not state.get("requirement_check")


def test_si_dale_goes_on_even_when_the_model_misses_the_yes() -> None:
    llm = MisreadingModel(THAMES.id, {"si dale"}, reads_yes_no=False)
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]), llm=llm)
    up_to_the_requirement(chat)

    slots = chat.say("si dale")

    assert slots[0]["slots"], slots
    assert requirement_questions(chat) == ["requirement_check"]


def test_no_after_the_requirement_offers_what_fits_even_if_read_as_a_pick() -> None:
    llm = MisreadingModel(THAMES.id, {"no"})
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]), llm=llm)
    up_to_the_requirement(chat)

    alternative = chat.say("no")

    assert chat.intents()[-1] == "offer_fitting"
    assert "Honduras 4800" in alternative[0]["text"]
    assert requirement_questions(chat) == ["requirement_check"]


def test_no_with_nothing_else_that_fits_says_nothing_fits() -> None:
    llm = MisreadingModel(THAMES.id, {"no puedo"}, reads_yes_no=False)
    chat = Chat(search=PolicySearch([THAMES]), llm=llm)
    up_to_the_requirement(chat)

    chat.say("no puedo")

    assert chat.intents()[-1] == "no_fit"
    assert requirement_questions(chat) == ["requirement_check"]


def test_an_unclear_answer_gets_one_differently_worded_question_then_goes_on() -> None:
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]))
    check = up_to_the_requirement(chat)

    again = chat.say("mmm capaz, lo tengo que ver")
    assert chat.intents()[-1] == "requirement_confirm"
    assert again[0]["text"] != check[0]["text"]
    assert chat.state()["asked_key"] == PUEDE_CUMPLIR

    chat.say("mmm todavía lo estoy viendo")

    # Asked twice in different words, never a third time: the conversation goes on.
    assert requirement_questions(chat) == ["requirement_check", "requirement_confirm"]
    assert not chat.state().get("requirement_check")


def test_an_unclear_answer_then_a_yes_gets_the_visit_times() -> None:
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]))
    up_to_the_requirement(chat)
    chat.say("mmm capaz, lo tengo que ver")

    slots = chat.say("dale, lo consigo")

    assert slots[0]["slots"], slots
    assert chat.state()["answers"]["acepta_requisitos"] == ["garantia"]


def test_the_same_requirement_is_never_asked_twice_for_the_same_card() -> None:
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]))
    up_to_the_requirement(chat)
    chat.say("no puedo")
    assert chat.intents()[-1] == "offer_fitting"

    chat.say("Me interesa la de Thames")

    # They know what it asks and chose it anyway: its visit times, the team sees the mismatch.
    assert requirement_questions(chat) == ["requirement_check"]
    assert chat.intents()[-1] == "offer_slots"
    assert chat.state()["property_matches"][THAMES.id]["status"] == "no_cumple"


def test_choosing_the_same_card_again_never_repeats_its_decisive_question() -> None:
    chat = Chat(search=PolicySearch([THAMES, HONDURAS]))
    for text in ["Hola", "Quiero alquilar con garantía propietaria", "Palermo"]:
        chat.say(text)
    chat.say("Me interesa la de Thames")
    chat.say("Me interesa la de Thames")

    assert chat.asked().count("plazo_meses") == 1
