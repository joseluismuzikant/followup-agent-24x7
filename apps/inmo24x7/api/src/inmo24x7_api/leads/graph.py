"""The inmo24x7 lead graph.

START -> extract -> respond -> END, once per inbound message.

The flow is decided here in code (`plan_turn`); the language model only reads values out of
the message (`extract`) and words each reply for an intent this module chose. Tools come from
the registry in `tools.py`. Rules enforced here, not in prompts:
- options are shown before asking for personal data;
- each message asks at most one thing;
- property links come only from the search results (own links or the sample pages);
- after a hand-off the agent answers politely and never proposes a visit again.
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
from followup_core.tenancy.domain.agent_config import QualificationQuestion
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from ..properties.domain.property import Currency, Operation
from ..properties.domain.search import PropertyMatch, PropertyQuery
from .display import price_label
from .domain.lead import HandOffReason
from .tools import (
    HAND_OFF,
    PROPOSE_VISIT,
    SAVE_CONTACT,
    SEARCH_PROPERTIES,
    HandOffInput,
    HandOffResult,
    ProposeVisitInput,
    SaveContactInput,
    SearchPropertiesInput,
    VisitProposal,
)

# Questions whose answers must be known before showing properties, when enabled.
REQUIRED_FILTERS = ("operation", "zone")
MAX_CONTACT_LENGTH = 120
MAX_NAME_LENGTH = 80


class LeadState(TypedDict):
    inbound: str
    outbox: list[dict[str, Any]]
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


@dataclass(frozen=True, slots=True)
class Step:
    intent: ReplyIntent
    question: QualificationQuestion | None = None


def enabled_questions(context: GraphContext) -> list[QualificationQuestion]:
    return [q for q in context.turn.agent_config.qualification_questions if q.enabled]


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


def plan_turn(state: LeadState, questions: Sequence[QualificationQuestion]) -> list[Step]:
    """The intents of this turn, in order. Each step becomes one outbound message, and only
    one step per turn asks something, so a message never asks two things."""
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
        # A (different) property: offer its slots; picking one later replaces the visit.
        return [Step(ReplyIntent.OFFER_SLOTS)]

    answers = state.get("answers") or {}
    pending = next((q for q in questions if q.key not in answers), None)
    enabled_keys = {q.key for q in questions}
    required = [key for key in REQUIRED_FILTERS if key in enabled_keys]
    filters_ready = all(key in answers for key in required) if required else pending is None

    if filters_ready and not state.get("properties_presented"):
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


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text if 0 < len(text) <= limit else None


def extract(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    context = runtime.context
    turn = context.turn
    if state.get("hand_off_reason") == HandOffReason.HUMAN:
        return {}
    answers = dict(state.get("answers") or {})
    handed_off = bool(state.get("hand_off_reason"))
    pending = [] if handed_off else [q for q in enabled_questions(context) if q.key not in answers]
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
            questions=pending,
            transcript=turn.transcript,
            latest=state["inbound"],
            asked_key=state.get("asked_key"),
            wants_name=wants_name,
            wants_contact=wants_contact,
            choices=offered,
        )
    )
    update["turn_choice"] = selected_choice(turn.choice_id, result.choice_id, offered)
    update["turn_wants_human"] = result.wants_human
    if handed_off:
        return update

    for question in pending:
        value = parse_answer(question, result.values.get(question.key))
        if value is not None:
            answers[question.key] = value
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


def respond(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    context = runtime.context
    turn = context.turn
    config = turn.agent_config
    questions = enabled_questions(context)
    answers = state.get("answers") or {}
    steps = plan_turn(state, questions)
    update: dict[str, Any] = {}
    facts: dict[str, str] = {"visitor_name": state.get("visitor_name") or ""}

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

    outbox: list[dict[str, Any]] = []
    asked_key: str | None = None
    for step in steps:
        # Facts belong to their own step: a slot noted in this turn must not leak into the
        # hand-off message that follows it.
        facts = {"visitor_name": state.get("visitor_name") or ""}
        payload: dict[str, Any] | None = None
        intent = step.intent

        if intent is ReplyIntent.PRESENT_OPTIONS:
            matches = context.tools.call(
                SEARCH_PROPERTIES,
                SearchPropertiesInput(
                    turn.business.tenant_id, _query(answers, {q.key for q in questions})
                ),
            )
            update["properties_presented"] = True
            if not matches:
                intent = ReplyIntent.NO_OPTIONS
            else:
                cards = [_card_payload(match) for match in matches]
                payload = {"cards": cards}
                update["offered_cards"] = [{"id": c["id"], "label": card_label(c)} for c in cards]
                update["shown_property_ids"] = [
                    *(state.get("shown_property_ids") or []),
                    *(card["id"] for card in cards),
                ]

        elif intent is ReplyIntent.OFFER_SLOTS:
            card = _card(state, state.get("turn_choice"))
            assert card is not None
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
            outbox.append({"text": reply(Step(intent)), "payload": None})
            outbox.append({"text": result.event, "payload": None, "author": "system"})
            continue

        outbox.append({"text": reply(Step(intent, step.question)), "payload": payload})
        if step.question is not None:
            asked_key = step.question.key
        elif intent is ReplyIntent.ASK_NAME:
            asked_key = NAME_KEY
        elif intent in (ReplyIntent.ASK_CONTACT, ReplyIntent.INVALID_CONTACT):
            asked_key = CONTACT_KEY

    # A lead who asks for a person after another kind of hand-off still gets human_requested.
    if state.get("hand_off_reason") and state.get("turn_wants_human"):
        update["hand_off_reason"] = HandOffReason.HUMAN.value

    return {
        **update,
        "outbox": outbox,
        "asked_key": asked_key,
        "last_intent": steps[-1].intent.value,
        "turns": state.get("turns", 0) + 1,
        "turn_choice": None,
        "turn_wants_human": False,
        "turn_contact_invalid": False,
    }


def build_lead_graph() -> StateGraph[Any, Any, Any, Any]:
    graph = StateGraph(LeadState, context_schema=GraphContext)
    graph.add_node("extract", extract)
    graph.add_node("respond", respond)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "respond")
    graph.add_edge("respond", END)
    return graph
