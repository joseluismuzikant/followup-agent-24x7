"""The inmo24x7 lead graph.

START -> extract -> respond -> END, once per inbound message.

The flow is decided here in code (`plan_turn`); the language model only reads values out of
the message (`extract`) and words each reply for an intent this module chose. Tools come from
the registry in `tools.py`. Rules enforced here, not in prompts:
- options are shown before asking for personal data;
- each message asks at most one thing (a greeting without a question asks nothing);
- one message per idea: a slot noted in the turn that hands off also carries the hand-off;
- property links come only from the search results (own links or the sample pages);
- after a hand-off the agent answers politely and never proposes a visit again;
- property conditions (leads/conditions.py): the lead's situation is captured whenever they
  mention it; options are ordered what-fits-first but never hidden; when the lead chooses a
  property, Sofía asks only the one question that property needs, and before offering visit
  times she says plainly which requirement they do not meet (when the agency wants it);
  when every option fails on the same requirement she asks about it once;
- "BAJA" ("no me escriban más", or the model's `wants_opt_out`): one fixed confirmation,
  nothing else, and `opt_out` tells the channel to stop writing to that contact.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from followup_core.conversation.domain.answers import normalize, parse_answer
from followup_core.conversation.domain.llm import (
    CONTACT_KEY,
    NAME_KEY,
    Choice,
    ExtractionRequest,
    ReplyIntent,
    ReplyRequest,
)
from followup_core.conversation.infrastructure.langgraph_runtime import GraphContext
from followup_core.messaging.domain.opt_out import OPT_OUT_CONFIRMATION, is_opt_out
from followup_core.tenancy.domain.agent_config import QualificationQuestion
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from ..properties.domain.conditions import (
    Match,
    MatchStatus,
    PropertyConditions,
    common_failure,
    evaluate,
)
from ..properties.domain.property import Currency, Operation
from ..properties.domain.search import PropertyMatch, PropertyQuery
from .conditions import (
    ACCEPTED,
    CONDITION_KEYS,
    CONFIRMATIONS,
    PUEDE_CUMPLIR,
    VER_ALTERNATIVAS,
    facts_for,
    gate_question,
    lead_conditions,
)
from .display import money, price_label
from .domain.lead import HandOffReason
from .tools import (
    CONDITION_POLICY,
    HAND_OFF,
    PROPOSE_VISIT,
    SAVE_CONTACT,
    SEARCH_PROPERTIES,
    ConditionPolicy,
    ConditionPolicyInput,
    HandOffInput,
    HandOffResult,
    ProposeVisitInput,
    SaveContactInput,
    SearchPropertiesInput,
    VisitProposal,
)

# Questions whose answers must be known before showing properties, when enabled.
REQUIRED_FILTERS = ("operation", "zone")
# Questions that only make sense when buying: never asked once the lead said they rent
# ("mortgage_approved" is the old name of necesita_credito).
SALE_ONLY_QUESTIONS = frozenset({"mortgage_approved"})
_ORDINALS = ("primera", "segunda", "tercera")
MAX_CONTACT_LENGTH = 120
MAX_NAME_LENGTH = 80


class LeadState(TypedDict):
    inbound: str
    outbox: list[dict[str, Any]]
    # Set by `respond` for the channel (transient, like inbound and outbox): the message
    # asked not to be written to again.
    opt_out: NotRequired[bool]
    # The lead said "BAJA" this turn (`extract`); `respond` confirms and clears it.
    turn_opt_out: NotRequired[bool]
    answers: NotRequired[dict[str, Any]]
    visitor_name: NotRequired[str | None]
    contact: NotRequired[str | None]
    shown_property_ids: NotRequired[list[str]]
    properties_presented: NotRequired[bool]
    # The cards of the last search, offered as choices: [{"id", "label"}].
    offered_cards: NotRequired[list[dict[str, Any]]]
    # Slots offered for one property: {"property_id", "property_label", "slots": [...]}.
    visit_offer: NotRequired[dict[str, Any] | None]
    visit_invited: NotRequired[bool]
    # The slot the lead picked: {"property_id", "property_label", "starts_at", "label"}.
    visit: NotRequired[dict[str, Any] | None]
    hand_off_reason: NotRequired[str | None]
    asked_key: NotRequired[str | None]
    last_intent: NotRequired[str | None]
    turns: NotRequired[int]
    # What `extract` read from this turn's message; `respond` clears them.
    turn_choice: NotRequired[str | None]
    turn_wants_human: NotRequired[bool]
    turn_contact_invalid: NotRequired[bool]
    # The lead's yes / no to "¿Podrías conseguirlo?" and to the "nothing fits" question.
    turn_can_meet: NotRequired[bool | None]
    turn_wants_alternatives: NotRequired[bool | None]
    # Conditions (leads/conditions.py). The card chosen while a decisive question is pending,
    # and the questions already asked about it.
    pending_card: NotRequired[str | None]
    gate_asked: NotRequired[list[str]]
    # A requirement the lead was told about before the visit: {"card_id", "requirement",
    # "asks"}; waiting for their yes or no.
    requirement_check: NotRequired[dict[str, Any] | None]
    # "Nothing fits" was asked (once per conversation): {"requirement", "asks"}.
    relax_offer: NotRequired[dict[str, Any] | None]
    relax_asked: NotRequired[bool]
    # The match of each card shown (Match.to_json()), as the agent knew it.
    property_matches: NotRequired[dict[str, dict[str, Any]]]
    chosen_property_ids: NotRequired[list[str]]
    # "mismatch" / "visit_avoided" / "no_fit" with their property id, for Inicio's counts.
    condition_events: NotRequired[list[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class Step:
    intent: ReplyIntent
    question: QualificationQuestion | None = None
    # The card this step is about (a decisive question, a requirement, its visit times).
    card_id: str | None = None
    # REQUIREMENT_CHECK / ASK_RELAX: {"requirement", "asks"}.
    failure: dict[str, Any] | None = None
    # PRESENT_OPTIONS again after the lead accepted a requirement ("nothing fits": yes).
    again: bool = False


def enabled_questions(context: GraphContext) -> list[QualificationQuestion]:
    return [q for q in context.turn.agent_config.qualification_questions if q.enabled]


def applicable_questions(
    questions: Sequence[QualificationQuestion], answers: dict[str, Any]
) -> list[QualificationQuestion]:
    """The questions asked up front, in order. The conditions' active questions are not
    among them: they are asked only when the chosen property needs them."""
    upfront = [q for q in questions if q.key not in CONDITION_KEYS]
    if _operation(answers.get("operation")) is not Operation.RENT:
        return upfront
    return [q for q in upfront if q.key not in SALE_ONLY_QUESTIONS]


def _card_conditions(card: dict[str, Any]) -> PropertyConditions:
    return PropertyConditions.from_json(card.get("conditions"))


def _card_operation(card: dict[str, Any]) -> Operation | None:
    value = card.get("operation")
    return Operation(value) if value in (Operation.RENT.value, Operation.SALE.value) else None


def card_match(card: dict[str, Any], answers: dict[str, Any]) -> Match:
    return evaluate(lead_conditions(answers), _card_conditions(card))


def gate_step(
    state: LeadState,
    card: dict[str, Any],
    questions: Sequence[QualificationQuestion],
    policy: ConditionPolicy,
) -> Step:
    """What happens when the lead chooses `card`: the one question it still needs, the
    requirement they do not meet, or its visit times."""
    answers = state.get("answers") or {}
    asked = (state.get("gate_asked") or []) if state.get("pending_card") == card["id"] else []
    question = gate_question(
        _card_conditions(card),
        _card_operation(card),
        answers,
        {q.key for q in questions},
        asked,
    )
    if question is not None:
        return Step(ReplyIntent.ASK, question, card_id=card["id"])
    match = card_match(card, answers)
    if match.status is MatchStatus.NO_CUMPLE and policy.warn_before_visit:
        failure = match.failed[0]
        return Step(
            ReplyIntent.REQUIREMENT_CHECK,
            card_id=card["id"],
            failure={"requirement": failure.requirement.value, "asks": failure.asks},
        )
    return Step(ReplyIntent.OFFER_SLOTS, card_id=card["id"])


def _fitting_cards(state: LeadState, excluding: str | None) -> list[dict[str, Any]]:
    answers = state.get("answers") or {}
    return [
        card
        for card in state.get("offered_cards") or []
        if card["id"] != excluding and card_match(card, answers).status is not MatchStatus.NO_CUMPLE
    ]


def _slot(state: LeadState, choice_id: str | None) -> dict[str, Any] | None:
    offer = state.get("visit_offer")
    if not offer or not choice_id:
        return None
    return next((slot for slot in offer["slots"] if slot["id"] == choice_id), None)


def _card(state: LeadState, choice_id: str | None) -> dict[str, Any] | None:
    if not choice_id:
        return None
    return next(
        (card for card in state.get("offered_cards") or [] if card["id"] == choice_id), None
    )


def offered_choices(state: LeadState) -> list[Choice]:
    """What the lead can pick: the slots on offer first, then the shown cards. After the
    hand-off only the slots of the existing offer remain (to change the time); no new
    property is offered."""
    offer = state.get("visit_offer")
    slots = [Choice(slot["id"], slot["label"]) for slot in offer["slots"]] if offer else []
    if state.get("hand_off_reason"):
        return slots
    cards = [Choice(card["id"], card["label"]) for card in state.get("offered_cards") or []]
    return [*slots, *cards]


def selected_choice(
    tapped: str | None, guessed: str | None, offered: Sequence[Choice]
) -> str | None:
    """The one place both channels resolve a pick: a tapped button (the simulator's slot
    buttons, WhatsApp reply buttons) wins over the model's reading of the text, and only ids
    the agent actually offered count."""
    ids = {choice.id for choice in offered}
    for candidate in (tapped, guessed):
        if candidate in ids:
            return candidate
    return None


def _changes_visit(state: LeadState, slot: dict[str, Any] | None) -> bool:
    """A picked slot that is not the visit already noted (a new time or a new property)."""
    if slot is None:
        return False
    visit = state.get("visit")
    offer = state.get("visit_offer") or {}
    return not visit or (visit["starts_at"], visit["property_id"]) != (
        slot["starts_at"],
        offer.get("property_id"),
    )


def plan_turn(
    state: LeadState,
    questions: Sequence[QualificationQuestion],
    policy: ConditionPolicy | None = None,
) -> list[Step]:
    """The intents of this turn, in order. Each step becomes one outbound message, and only
    one step per turn asks something, so a message never asks two things."""
    policy = policy or ConditionPolicy()
    first_turn = state.get("turns", 0) == 0
    choice = state.get("turn_choice")
    slot = _slot(state, choice)
    if state.get("hand_off_reason"):
        # Changing the time of the visit already proposed is still possible.
        if _changes_visit(state, slot) and not state.get("turn_wants_human"):
            return [Step(ReplyIntent.SLOT_CHOSEN)]
        return [Step(ReplyIntent.AFTER_HAND_OFF)]
    if state.get("turn_wants_human"):
        return _with_greeting([Step(ReplyIntent.HAND_OFF)], first_turn)

    steps: list[Step] = []
    visit = bool(state.get("visit"))
    offer = state.get("visit_offer") or {}
    card = _card(state, choice)
    if _changes_visit(state, slot):
        # A first pick, or a different slot that replaces the visit already noted.
        steps.append(Step(ReplyIntent.SLOT_CHOSEN))
        visit = True
    elif card is not None and card["id"] != offer.get("property_id"):
        # A (different) property: what it still needs, its requirements, then its slots;
        # picking one later replaces the visit.
        return [gate_step(state, card, questions, policy)]
    else:
        check = state.get("requirement_check")
        can_meet = state.get("turn_can_meet")
        if check and can_meet is not None:
            if can_meet:
                return [Step(ReplyIntent.OFFER_SLOTS, card_id=check["card_id"])]
            fitting = _fitting_cards(state, check["card_id"])
            if fitting:
                return [Step(ReplyIntent.OFFER_FITTING, card_id=check["card_id"])]
            return [Step(ReplyIntent.NO_FIT, card_id=check["card_id"])]
        pending_card = _card(state, state.get("pending_card"))
        if pending_card is not None and not visit:
            # The answer to the decisive question: go on with that property.
            return [gate_step(state, pending_card, questions, policy)]
        relax = state.get("relax_offer")
        wants_alternatives = state.get("turn_wants_alternatives")
        if relax and wants_alternatives is not None:
            if wants_alternatives:
                steps.append(Step(ReplyIntent.PRESENT_OPTIONS, again=True))
            else:
                steps.append(Step(ReplyIntent.NO_FIT))

    answers = state.get("answers") or {}
    pending = next(
        (q for q in applicable_questions(questions, answers) if q.key not in answers), None
    )
    enabled_keys = {q.key for q in questions}
    required = [key for key in REQUIRED_FILTERS if key in enabled_keys]
    filters_ready = all(key in answers for key in required) if required else pending is None

    relaxed = any(
        step.intent in (ReplyIntent.PRESENT_OPTIONS, ReplyIntent.NO_FIT) for step in steps
    )
    if filters_ready and not state.get("properties_presented") and not relaxed:
        steps.append(Step(ReplyIntent.PRESENT_OPTIONS))
    if pending is not None and not visit:
        steps.append(Step(ReplyIntent.ASK, pending))
    elif not state.get("visitor_name"):
        steps.append(Step(ReplyIntent.ASK_NAME))
    elif not state.get("contact"):
        invalid = state.get("turn_contact_invalid")
        steps.append(Step(ReplyIntent.INVALID_CONTACT if invalid else ReplyIntent.ASK_CONTACT))
    elif (
        not visit
        and state.get("offered_cards")
        and not state.get("visit_offer")
        and not state.get("visit_invited")
    ):
        steps.append(Step(ReplyIntent.OFFER_VISIT))
    else:
        steps.append(Step(ReplyIntent.HAND_OFF))
    return _with_greeting(steps, first_turn)


def _with_greeting(steps: list[Step], first_turn: bool) -> list[Step]:
    if not first_turn:
        return steps
    if steps[0].intent is ReplyIntent.ASK:
        return [Step(ReplyIntent.GREET, steps[0].question), *steps[1:]]
    return [Step(ReplyIntent.GREET), *steps]


def _folds_hand_off(steps: Sequence[Step], index: int) -> bool:
    """A HAND_OFF right after SLOT_CHOSEN: the slot's message already says that a person
    follows up, so the hand-off sends no message of its own (two in a row said the same)."""
    return (
        steps[index].intent is ReplyIntent.SLOT_CHOSEN
        and index + 1 < len(steps)
        and steps[index + 1].intent is ReplyIntent.HAND_OFF
    )


def looking_for_fact(answers: dict[str, Any]) -> str:
    """What the lead asked for, in words the greeting can repeat without inventing anything:
    "2 ambientes en alquiler en Palermo hasta $900.000". Empty when nothing is known."""
    parts: list[str] = []
    rooms = answers.get("rooms")
    operation = _operation(answers.get("operation"))
    if isinstance(rooms, int) and rooms > 0:
        parts.append("monoambientes" if rooms == 1 else f"{rooms} ambientes")
    if operation is Operation.RENT:
        parts.append("en alquiler" if parts else "alquiler")
    elif operation is Operation.SALE:
        parts.append("en venta" if parts else "compra")
    if zone := answers.get("zone"):
        parts.append(f"en {zone}")
    budget = answers.get("budget")
    if isinstance(budget, dict) and "amount" in budget and "currency" in budget:
        parts.append(f"hasta {money(budget['amount'], budget['currency'])}")
    return " ".join(parts)


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text if 0 < len(text) <= limit else None


def extract(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    context = runtime.context
    turn = context.turn
    if is_opt_out(state["inbound"]):
        # A clear "BAJA": no model call, nothing else is read from this message.
        return {"turn_opt_out": True}
    if state.get("hand_off_reason") == HandOffReason.HUMAN:
        return {}
    answers = dict(state.get("answers") or {})
    handed_off = bool(state.get("hand_off_reason"))
    questions = applicable_questions(enabled_questions(context), answers)
    pending = [] if handed_off else [q for q in questions if q.key not in answers]
    # The lead's situation is read from every message, asked or not (never guessed).
    facts = (
        []
        if handed_off
        else [q for q in facts_for(_operation(answers.get("operation"))) if q.key not in answers]
    )
    confirmation = CONFIRMATIONS.get(state.get("asked_key") or "")
    update: dict[str, Any] = {}
    # The channel may already know how to reach the visitor (WhatsApp: their own number),
    # so the agent never asks for it.
    if not state.get("contact") and turn.visitor_contact:
        update["contact"] = turn.visitor_contact
    wants_name = not handed_off and not state.get("visitor_name")
    wants_contact = not handed_off and not state.get("contact") and "contact" not in update
    offered = offered_choices(state)

    result = context.llm.extract(
        ExtractionRequest(
            questions=[*pending, *facts, *([confirmation] if confirmation else [])],
            transcript=turn.transcript,
            latest=state["inbound"],
            asked_key=state.get("asked_key"),
            wants_name=wants_name,
            wants_contact=wants_contact,
            choices=offered,
        )
    )
    if result.wants_opt_out:
        return {"turn_opt_out": True}
    update["turn_choice"] = selected_choice(turn.choice_id, result.choice_id, offered)
    update["turn_wants_human"] = result.wants_human
    if handed_off:
        return update

    for question in [*pending, *facts]:
        value = parse_answer(question, result.values.get(question.key))
        if value is not None:
            answers[question.key] = value
    if confirmation is not None:
        said = parse_answer(confirmation, result.values.get(confirmation.key))
        key = "turn_can_meet" if confirmation.key == PUEDE_CUMPLIR else "turn_wants_alternatives"
        update[key] = said if isinstance(said, bool) else None
    update["answers"] = answers
    # A message that picks a card or a slot is that pick, never a name or a contact.
    picked = update["turn_choice"] is not None
    if wants_name and not picked and (name := _clean(result.visitor_name, MAX_NAME_LENGTH)):
        update["visitor_name"] = name
    if wants_contact and not picked and (raw := _clean(result.contact, MAX_CONTACT_LENGTH)):
        contact = context.tools.call(SAVE_CONTACT, SaveContactInput(raw))
        if contact:
            update["contact"] = contact
        else:
            update["turn_contact_invalid"] = True
    return update


def _operation(answer: Any) -> Operation | None:
    text = normalize(str(answer)) if answer is not None else ""
    if text.startswith("compr") or text.startswith("vent"):
        return Operation.SALE
    if text.startswith("alquil"):
        return Operation.RENT
    return None


def _query(answers: dict[str, Any], enabled_keys: set[str]) -> PropertyQuery:
    """Built-in filters only; custom_* answers never filter properties."""
    budget = answers.get("budget") if "budget" in enabled_keys else None
    rooms = answers.get("rooms") if "rooms" in enabled_keys else None
    return PropertyQuery(
        operation=_operation(answers.get("operation")),
        zone=answers.get("zone"),
        max_budget=budget["amount"] if budget else None,
        budget_currency=Currency(budget["currency"]) if budget else None,
        rooms=rooms if isinstance(rooms, int) else None,
        lead=lead_conditions(answers),
    )


def _card_payload(match: PropertyMatch) -> dict[str, Any]:
    item = match.listing
    return {
        "id": item.id,
        "title": item.title,
        "address": item.address,
        "operation": item.operation.value,
        "zone": item.zone,
        "price_label": price_label(item),
        "rooms": item.rooms,
        # Always the listing's own link (or the sample's local page); never generated.
        "link": item.link,
        "over_budget": match.over_budget,
        "is_sample": item.is_sample,
    }


def card_label(card: dict[str, Any]) -> str:
    return f"{card['title']} · {card['address']}"


def feature_line(matches: Sequence[PropertyMatch]) -> str:
    """One short positive line ("La primera acepta mascotas"), never a "no cumple"."""
    for position, match in enumerate(matches[: len(_ORDINALS)]):
        if match.match.status is MatchStatus.CUMPLE and match.match.features:
            return f"La {_ORDINALS[position]} {match.match.features[0]}."
    return ""


def plural(asks: str) -> str:
    """ "pide contrato de 2 años" -> "piden contrato de 2 años" (said of every option)."""
    for one, many in (("pide ", "piden "), ("no acepta ", "no aceptan ")):
        if asks.startswith(one):
            return many + asks.removeprefix(one)
    return asks


def _event(kind: str, card_id: str | None) -> dict[str, Any]:
    return {"kind": kind, "property_id": card_id}


def respond(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    if state.get("turn_opt_out"):
        # Fixed text (never the model's wording), and nothing else this turn.
        return {
            "outbox": [{"text": OPT_OUT_CONFIRMATION, "payload": None}],
            "opt_out": True,
            "turn_opt_out": False,
            "asked_key": None,
            "turns": state.get("turns", 0) + 1,
        }
    context = runtime.context
    turn = context.turn
    config = turn.agent_config
    questions = enabled_questions(context)
    answers: dict[str, Any] = dict(state.get("answers") or {})
    policy: ConditionPolicy = context.tools.call(
        CONDITION_POLICY, ConditionPolicyInput(turn.business.tenant_id)
    )
    steps = plan_turn(state, questions, policy)
    update: dict[str, Any] = {}
    facts: dict[str, str] = {"visitor_name": state.get("visitor_name") or ""}
    events: list[dict[str, Any]] = list(state.get("condition_events") or [])
    chosen: list[str] = list(state.get("chosen_property_ids") or [])

    def reply(step: Step) -> str:
        return context.llm.compose_reply(
            ReplyRequest(
                intent=step.intent,
                tone=config.tone,
                agent_name=config.agent_name,
                business_name=turn.business.business_name,
                question=step.question,
                facts={key: value for key, value in facts.items() if value},
            )
        ).text

    def choose(card_id: str | None) -> None:
        if card_id and card_id not in chosen:
            chosen.append(card_id)

    def accept(requirement: str) -> None:
        accepted = list(answers.get(ACCEPTED) or [])
        if requirement not in accepted:
            answers[ACCEPTED] = [*accepted, requirement]
        update["answers"] = answers

    def card_of(card_id: str | None) -> dict[str, Any] | None:
        return next(
            (card for card in state.get("offered_cards") or [] if card["id"] == card_id), None
        )

    outbox: list[dict[str, Any]] = []
    asked_key: str | None = None
    for index, step in enumerate(steps):
        # Facts belong to their own step: a slot noted in this turn must not leak into the
        # hand-off message that follows it.
        facts = {"visitor_name": state.get("visitor_name") or ""}
        payload: dict[str, Any] | None = None
        intent = step.intent
        relax: dict[str, Any] | None = None

        if intent is ReplyIntent.GREET:
            facts["looking_for"] = looking_for_fact(answers)

        elif intent is ReplyIntent.ASK and step.card_id is not None:
            # The decisive question of the chosen property: its slots come after the answer.
            assert step.question is not None
            choose(step.card_id)
            update["pending_card"] = step.card_id
            previous = state.get("gate_asked") if state.get("pending_card") == step.card_id else []
            update["gate_asked"] = [*(previous or []), step.question.key]

        elif intent is ReplyIntent.PRESENT_OPTIONS:
            if step.again:
                offer = state.get("relax_offer") or {}
                if offer.get("requirement"):
                    accept(offer["requirement"])
                update["relax_offer"] = None
            matches = context.tools.call(
                SEARCH_PROPERTIES,
                SearchPropertiesInput(
                    turn.business.tenant_id,
                    _query(answers, {q.key for q in questions}),
                ),
            )
            update["properties_presented"] = True
            if not matches:
                intent = ReplyIntent.NO_OPTIONS
            else:
                cards = [_card_payload(match) for match in matches]
                payload = {"cards": cards}
                update["offered_cards"] = [
                    {
                        "id": card["id"],
                        "label": card_label(card),
                        "operation": card["operation"],
                        # Effective conditions as shown: the inbox never recomputes them.
                        "conditions": match.listing.conditions.to_json(),
                    }
                    for card, match in zip(cards, matches, strict=True)
                ]
                update["shown_property_ids"] = [
                    *(state.get("shown_property_ids") or []),
                    *(card["id"] for card in cards),
                ]
                facts["feature_line"] = feature_line(matches)
                failure = common_failure([match.match for match in matches])
                if (
                    failure is not None
                    and policy.offer_alternatives
                    and not state.get("relax_asked")
                    and not step.again
                ):
                    relax = {"requirement": failure.requirement.value, "asks": failure.asks}

        elif intent is ReplyIntent.REQUIREMENT_CHECK:
            card = card_of(step.card_id)
            assert card is not None and step.failure is not None
            choose(card["id"])
            update["pending_card"] = None
            update["requirement_check"] = {"card_id": card["id"], **step.failure}
            events.append(_event("mismatch", card["id"]))
            facts["option"] = card["label"]
            facts["requirement"] = step.failure["asks"]
            note = _card_conditions(card).condiciones
            if note:
                facts["conditions_note"] = note

        elif intent is ReplyIntent.OFFER_FITTING:
            events.append(_event("visit_avoided", step.card_id))
            update["requirement_check"] = None
            fitting = _fitting_cards(state, step.card_id)
            facts["options"] = " y ".join(card["label"] for card in fitting)

        elif intent is ReplyIntent.NO_FIT:
            if state.get("requirement_check"):
                events.append(_event("visit_avoided", step.card_id))
            else:
                events.append(_event("no_fit", None))
            update["requirement_check"] = None
            update["relax_offer"] = None
            # Nothing to visit: never invite to one afterwards.
            update["visit_invited"] = True

        elif intent is ReplyIntent.OFFER_SLOTS:
            card_id = step.card_id or state.get("turn_choice")
            card = card_of(card_id)
            assert card is not None
            check = state.get("requirement_check")
            if check and check.get("card_id") == card["id"]:
                # "Sí, lo consigo": noted for the team, and the visit goes on as today.
                accept(check["requirement"])
                update["requirement_check"] = None
            choose(card["id"])
            update["pending_card"] = None
            proposal: VisitProposal = context.tools.call(
                PROPOSE_VISIT,
                ProposeVisitInput(
                    property_id=card["id"],
                    property_label=card["label"],
                    team_hours=turn.business.team_hours,
                    timezone=turn.business.timezone,
                    now=turn.now,
                ),
            )
            if not proposal.slots:
                # No team hours at all: a person coordinates the visit.
                intent = ReplyIntent.HAND_OFF
            else:
                slots = [
                    {
                        "id": slot.id,
                        "label": slot.label,
                        "short_label": slot.short_label,
                        "starts_at": slot.starts_at,
                    }
                    for slot in proposal.slots
                ]
                update["visit_offer"] = {
                    "property_id": proposal.property_id,
                    "property_label": proposal.property_label,
                    "slots": slots,
                }
                facts["option"] = card["label"]
                facts["slots"] = " o ".join(slot["label"] for slot in slots)
                facts["after_hours"] = "sí" if proposal.after_hours else ""
                note = _card_conditions(card).condiciones
                if note:
                    facts["conditions_note"] = note
                payload = {
                    "slots": [
                        {"id": s["id"], "label": s["label"], "short_label": s["short_label"]}
                        for s in slots
                    ]
                }

        elif intent is ReplyIntent.SLOT_CHOSEN:
            offer = state.get("visit_offer") or {}
            slot = _slot(state, state.get("turn_choice")) or {}
            update["visit"] = {
                "property_id": offer.get("property_id"),
                "property_label": offer.get("property_label"),
                "starts_at": slot.get("starts_at"),
                "label": slot.get("label"),
            }
            facts["slot"] = slot.get("label", "")
            if _folds_hand_off(steps, index):
                facts["hand_off"] = "sí"

        elif intent is ReplyIntent.OFFER_VISIT:
            update["visit_invited"] = True

        if intent is ReplyIntent.HAND_OFF:
            if state.get("turn_wants_human"):
                reason = HandOffReason.HUMAN
            elif update.get("visit") or state.get("visit"):
                reason = HandOffReason.VISIT
            else:
                reason = HandOffReason.QUALIFIED
            result: HandOffResult = context.tools.call(HAND_OFF, HandOffInput(reason))
            update["hand_off_reason"] = result.reason.value
            if not (index > 0 and _folds_hand_off(steps, index - 1)):
                outbox.append({"text": reply(Step(intent)), "payload": None})
            outbox.append({"text": result.event, "payload": None, "author": "system"})
            continue

        outbox.append({"text": reply(Step(intent, step.question)), "payload": payload})
        if relax is not None:
            # Every option fails on the same requirement: ask about it once, and nothing else
            # this turn.
            update["relax_offer"] = relax
            update["relax_asked"] = True
            facts = {
                "visitor_name": state.get("visitor_name") or "",
                "requirement": plural(relax["asks"]),
            }
            outbox.append({"text": reply(Step(ReplyIntent.ASK_RELAX)), "payload": None})
            asked_key = VER_ALTERNATIVAS
            break
        if step.question is not None:
            asked_key = step.question.key
        elif intent is ReplyIntent.ASK_NAME:
            asked_key = NAME_KEY
        elif intent in (ReplyIntent.ASK_CONTACT, ReplyIntent.INVALID_CONTACT):
            asked_key = CONTACT_KEY
        elif intent is ReplyIntent.REQUIREMENT_CHECK:
            asked_key = PUEDE_CUMPLIR

    # A lead who asks for a person after another kind of hand-off still gets human_requested.
    if state.get("hand_off_reason") and state.get("turn_wants_human"):
        update["hand_off_reason"] = HandOffReason.HUMAN.value

    # How every card shown compares with what the lead said, as of this turn.
    cards = update.get("offered_cards") or state.get("offered_cards") or []
    matches = dict(state.get("property_matches") or {})
    for card in cards:
        matches[card["id"]] = card_match(card, answers).to_json()

    return {
        **update,
        "outbox": outbox,
        "asked_key": asked_key,
        "last_intent": steps[-1].intent.value,
        "turns": state.get("turns", 0) + 1,
        "turn_choice": None,
        "turn_wants_human": False,
        "turn_contact_invalid": False,
        "turn_can_meet": None,
        "turn_wants_alternatives": None,
        "property_matches": matches,
        "chosen_property_ids": chosen,
        "condition_events": events,
    }


def build_lead_graph() -> StateGraph[Any, Any, Any, Any]:
    graph = StateGraph(LeadState, context_schema=GraphContext)
    graph.add_node("extract", extract)
    graph.add_node("respond", respond)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "respond")
    graph.add_edge("respond", END)
    return graph
