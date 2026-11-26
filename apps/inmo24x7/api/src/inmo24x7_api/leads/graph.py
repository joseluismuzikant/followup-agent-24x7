"""The inmo24x7 lead graph.

START -> guard_input -> extract -> respond -> guard_output -> END, once per inbound message.

The governing rule: the model proposes text and values; this module decides, validates,
limits and persists. Limits, counters and termination are never in a prompt, never a model
output, and never changed by one.

- guard_input: the message normalised (core guards), suspicious patterns logged (codes
  only, never blocked), values from older checkpoints checked again.
- extract: one model call for values, validated here; only `EXTRACT_KEYS` are written.
- respond: `plan_turn` decides the steps; the model words each one. A turn that hit a limit
  (conversation/application/execution_guard.py) or whose model is down on the message's last
  attempt is worded with `safe_texts`.
- guard_output: every outbound text checked (length, links, contacts, income, grounding of
  answers); a failing one is replaced by its fixed text. Progress and the per-turn keys are
  settled here, at the end of the turn.

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
  nothing else, and `opt_out` tells the channel to stop writing to that contact;
- the website button ("Consultar por WhatsApp", properties/domain/reference.py): a first
  message that names one of the agency's published properties makes it the chosen one.
  Sofía greets naming it, asks only what that property still needs and goes on to its
  visit times; the lead's source is "web_button".
"""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, NotRequired, TypedDict

from followup_core.conversation.application.execution_guard import (
    ExecutionStopped,
    TerminationReason,
)
from followup_core.conversation.domain.answers import normalize, parse_answer
from followup_core.conversation.domain.errors import LlmUnavailableError
from followup_core.conversation.domain.guards import (
    find_amounts,
    find_contacts,
    find_urls,
    mentions_income,
    normalize_inbound,
    sanitize_untrusted,
    suspicion_flags,
)
from followup_core.conversation.domain.llm import (
    CONTACT_KEY,
    NAME_KEY,
    Choice,
    Extraction,
    ExtractionRequest,
    ReplyIntent,
    ReplyRequest,
)
from followup_core.conversation.infrastructure.langgraph_runtime import GraphContext
from followup_core.messaging.domain.opt_out import OPT_OUT_CONFIRMATION, is_opt_out
from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind
from followup_core.tenancy.domain.business_settings import ScheduleBlock, is_within_hours
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from ..properties.domain.conditions import (
    Match,
    MatchStatus,
    PropertyConditions,
    common_failure,
    condition_phrases,
    evaluate,
)
from ..properties.domain.property import Currency, Operation
from ..properties.domain.reference import read_web_reference
from ..properties.domain.search import Listing, PropertyMatch, PropertyQuery
from .conditions import (
    ACCEPTED,
    CONDITION_KEYS,
    CONFIRMATIONS,
    PUEDE_CUMPLIR,
    VER_ALTERNATIVAS,
    facts_for,
    gate_question,
    lead_conditions,
    read_yes_no,
)
from .display import money, price_label
from .domain.lead import HandOffReason
from .progress import (
    AFTER_HAND_OFF_QUIET_HOURS,
    REPEATED_INTENT_TURNS,
    StallAction,
    advance,
    stall_decision,
)
from .safe_texts import AGENT_FAILURE_TEXT, DEFERRED_ANSWER, safe_text
from .tools import (
    CONDITION_POLICY,
    FIND_REFERENCED_PROPERTY,
    HAND_OFF,
    PROPOSE_VISIT,
    SAVE_CONTACT,
    SEARCH_PROPERTIES,
    ConditionPolicy,
    ConditionPolicyInput,
    FindReferencedPropertyInput,
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
# A name: letters, spaces, apostrophes and hyphens only, at most four words.
MAX_NAME_LENGTH = 40
MAX_NAME_WORDS = 4
# A free-text answer (a zone): short, without links or role markers.
MAX_TEXT_ANSWER = 60
# Property strings that reach a prompt (titles and addresses are imported from CSV, Tokko
# or a portal page: untrusted).
MAX_PROPERTY_TEXT = 120
MAX_CONDITIONS_NOTE = 300
# An outbound text longer than this is replaced by its fixed text.
MAX_REPLY_LENGTH = 700
# The yes / no to OFFER_HUMAN ("¿Querés que te contacte una persona del equipo?").
QUIERE_PERSONA = "quiere_persona"
OFFER_HUMAN_QUESTION = QualificationQuestion(
    QUIERE_PERSONA, "Si quiere que lo contacte una persona del equipo", QuestionKind.BOOLEAN
)
# Answers the lead may change later, and that search again (1.4).
REFINABLE_KEYS = ("operation", "zone", "rooms", "budget")
# Reply intents whose message asks something (OFFER_HUMAN replaces the turn's question).
ASKING_INTENTS = frozenset(
    {
        ReplyIntent.ASK,
        ReplyIntent.ASK_NAME,
        ReplyIntent.ASK_CONTACT,
        ReplyIntent.INVALID_CONTACT,
        ReplyIntent.OFFER_VISIT,
        ReplyIntent.OFFER_SLOTS,
        ReplyIntent.REQUIREMENT_CHECK,
        ReplyIntent.REQUIREMENT_CONFIRM,
        ReplyIntent.OFFER_FITTING,
    }
)

logger = logging.getLogger("inmo24x7.lead_agent")
_NAME = re.compile(r"^[^\W\d_]+(?:['’ -][^\W\d_]+)*$")


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
    # "asks", "confirmed_once"}; waiting for their yes or no. "confirmed_once": an unclear
    # answer was already asked about again, in other words.
    requirement_check: NotRequired[dict[str, Any] | None]
    # Every requirement told about, as "<card id>:<requirement>": never told twice.
    requirements_asked: NotRequired[list[str]]
    # "Nothing fits" was asked (once per conversation): {"requirement", "asks"}.
    relax_offer: NotRequired[dict[str, Any] | None]
    relax_asked: NotRequired[bool]
    # The match of each card shown (Match.to_json()), as the agent knew it.
    property_matches: NotRequired[dict[str, dict[str, Any]]]
    chosen_property_ids: NotRequired[list[str]]
    # "mismatch" / "visit_avoided" / "no_fit" with their property id, for Inicio's counts.
    condition_events: NotRequired[list[dict[str, Any]]]
    # Where the lead came from: "web_button" (the website's "Consultar por WhatsApp").
    lead_source: NotRequired[str | None]
    # The card the first message named (the website button); Sofía greets naming it.
    referenced_card: NotRequired[str | None]
    # Per turn (guard_input and extract set them; guard_output resets them): suspicious
    # patterns (codes), whether the lead asked something and about what, whether they
    # changed a search answer, and the model being down on the message's last attempt.
    turn_flags: NotRequired[list[str]]
    turn_needs_answer: NotRequired[bool]
    turn_topic: NotRequired[str | None]
    turn_refine_search: NotRequired[bool]
    turn_agent_failure: NotRequired[bool]
    # Questions answered from the data, and deferred to the team ("lo consulto").
    answers_given: NotRequired[int]
    answers_deferred: NotRequired[int]
    # leads/progress.py: {stage, answered_keys_count, chosen_count, last_progress_turn,
    # last_intent, same_intent_turns}.
    progress: NotRequired[dict[str, Any]]
    # OFFER_HUMAN was asked (once per conversation).
    stall_offered: NotRequired[bool]
    # When the last reply after the hand-off went out (ISO datetime).
    after_hand_off_replied_at: NotRequired[str | None]
    # Transient: why the turn ended (the trace's outputs; never part of the snapshot).
    termination_reason: NotRequired[str]


# What `extract` may write. Anything else a model returns never reaches the state.
EXTRACT_KEYS = frozenset(
    {
        "turn_opt_out",
        "turn_choice",
        "turn_wants_human",
        "turn_contact_invalid",
        "turn_can_meet",
        "turn_wants_alternatives",
        "turn_needs_answer",
        "turn_topic",
        "turn_refine_search",
        "turn_agent_failure",
        "answers",
        "visitor_name",
        "contact",
        "lead_source",
        "offered_cards",
        "shown_property_ids",
        "properties_presented",
        "referenced_card",
    }
)


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
    # PRESENT_OPTIONS again because the lead changed a search answer.
    refine: bool = False
    # HAND_OFF: the reason when the planner decides it (stalled, agent failure).
    reason: HandOffReason | None = None
    # Logged when the conversation stalled ("conversation_stalled" / "conversation_limit").
    stall: str | None = None


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
    told = set(state.get("requirements_asked") or [])
    failures = [
        failure
        for failure in match.failed
        if requirement_key(card["id"], failure.requirement.value) not in told
    ]
    if failures and policy.warn_before_visit:
        # A requirement already told about this card is never told again: the lead chose it
        # knowing it (the team sees the mismatch).
        failure = failures[0]
        return Step(
            ReplyIntent.REQUIREMENT_CHECK,
            card_id=card["id"],
            failure={"requirement": failure.requirement.value, "asks": failure.asks},
        )
    return Step(ReplyIntent.OFFER_SLOTS, card_id=card["id"])


def requirement_key(card_id: str, requirement: str) -> str:
    return f"{card_id}:{requirement}"


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


def _answers_now(state: LeadState) -> bool:
    """ANSWER_QUESTION goes first: the lead asked something, did not opt out, the thread is
    not with a person on their request, and the message is not only a tapped button."""
    return (
        bool(state.get("turn_needs_answer"))
        and not state.get("turn_opt_out")
        and state.get("hand_off_reason") != HandOffReason.HUMAN.value
    )


def _progressing(state: LeadState) -> bool:
    """This turn's own message already moves the conversation: a new answer, a pick, a
    changed search or the answer to a requirement."""
    progress = state.get("progress") or {}
    known = progress.get("answered_keys_count")
    return (
        (known is not None and len(state.get("answers") or {}) > int(known))
        or state.get("turn_choice") is not None
        or bool(state.get("turn_refine_search"))
        or state.get("turn_can_meet") is not None
        or state.get("turn_wants_alternatives") is not None
    )


def plan_turn(
    state: LeadState,
    questions: Sequence[QualificationQuestion],
    policy: ConditionPolicy | None = None,
) -> list[Step]:
    """The intents of this turn, in order. Each step becomes one outbound message, and only
    one step per turn asks something, so a message never asks two things.

    Around the flow (`_flow_steps`): the model being down on the last attempt hands off; an
    answer to the lead's question goes first (it asks nothing); a conversation that stopped
    moving offers a person once (instead of the turn's own question) and later hands off
    (leads/progress.py)."""
    if state.get("turn_agent_failure"):
        return [Step(ReplyIntent.HAND_OFF, reason=HandOffReason.AGENT_FAILURE)]
    answer = _answers_now(state)
    if state.get("hand_off_reason"):
        # Changing the time of the visit already proposed is still possible.
        if _changes_visit(state, _slot(state, state.get("turn_choice"))) and not state.get(
            "turn_wants_human"
        ):
            return [Step(ReplyIntent.SLOT_CHOSEN)]
        # After a hand-off it may answer, but it never proposes anything.
        return [Step(ReplyIntent.ANSWER_QUESTION if answer else ReplyIntent.AFTER_HAND_OFF)]
    first_turn = state.get("turns", 0) == 0
    if state.get("turn_wants_human"):
        return _with_greeting([Step(ReplyIntent.HAND_OFF)], first_turn)

    steps = _flow_steps(state, questions, policy or ConditionPolicy())
    progress = state.get("progress") or {}
    repeated = (
        not _progressing(state)
        and steps[-1].intent is not ReplyIntent.AFTER_HAND_OFF
        and steps[-1].intent.value == progress.get("last_intent")
        and int(progress.get("same_intent_turns") or 0) + 1 >= REPEATED_INTENT_TURNS
    )
    decision = stall_decision(state, progressing=_progressing(state), repeated=repeated)
    if decision.action is StallAction.HAND_OFF:
        return [Step(ReplyIntent.HAND_OFF, reason=HandOffReason.STALLED, stall=decision.reason)]
    if answer:
        steps = _answer_first(steps)
    if decision.action is StallAction.OFFER_HUMAN:
        steps = _offer_human_instead(steps, decision.reason)
    return steps


def _answer_first(steps: list[Step]) -> list[Step]:
    """The answer right after the greeting (a greeting that asks gives its question to its
    own step, after the answer)."""
    answer = Step(ReplyIntent.ANSWER_QUESTION)
    if steps and steps[0].intent is ReplyIntent.GREET:
        greet = steps[0]
        rest = steps[1:]
        if greet.question is not None:
            rest = [Step(ReplyIntent.ASK, greet.question), *rest]
        return [Step(ReplyIntent.GREET), answer, *rest]
    return [answer, *steps]


def _offer_human_instead(steps: list[Step], reason: str | None) -> list[Step]:
    """OFFER_HUMAN replaces the turn's own question; a turn that asks nothing (a hand-off,
    nothing fits) gets nothing extra."""
    last = steps[-1]
    offer = Step(ReplyIntent.OFFER_HUMAN, stall=reason)
    if last.intent is ReplyIntent.GREET and last.question is not None:
        return [*steps[:-1], Step(ReplyIntent.GREET), offer]
    if last.intent in ASKING_INTENTS:
        return [*steps[:-1], offer]
    return steps


def _flow_steps(
    state: LeadState,
    questions: Sequence[QualificationQuestion],
    policy: ConditionPolicy,
) -> list[Step]:
    first_turn = state.get("turns", 0) == 0
    if state.get("turn_refine_search"):
        # A changed search answer starts the options again: whatever was pending about the
        # old ones (a requirement, a decisive question, "nothing fits") is dropped.
        state = {**state, "requirement_check": None, "pending_card": None, "relax_offer": None}
    choice = state.get("turn_choice")
    slot = _slot(state, choice)

    steps: list[Step] = []
    visit = bool(state.get("visit"))
    offer = state.get("visit_offer") or {}
    card = _card(state, choice)
    check = state.get("requirement_check")
    if card is not None and check and card["id"] == check["card_id"]:
        # The card whose requirement is pending, "picked" again ("si dale" read as a pick):
        # the answer to the requirement, not a new choice.
        card = None
    if _changes_visit(state, slot):
        # A first pick, or a different slot that replaces the visit already noted.
        steps.append(Step(ReplyIntent.SLOT_CHOSEN))
        visit = True
    elif card is not None and card["id"] != offer.get("property_id"):
        # A (different) property: what it still needs, its requirements, then its slots;
        # picking one later replaces the visit. Named in the first message (the website
        # button): greeted first, in a message of its own.
        gate = gate_step(state, card, questions, policy)
        return [Step(ReplyIntent.GREET), gate] if first_turn else [gate]
    else:
        can_meet = state.get("turn_can_meet")
        if check and can_meet is not None:
            if can_meet:
                return [Step(ReplyIntent.OFFER_SLOTS, card_id=check["card_id"])]
            fitting = _fitting_cards(state, check["card_id"])
            if fitting:
                return [Step(ReplyIntent.OFFER_FITTING, card_id=check["card_id"])]
            return [Step(ReplyIntent.NO_FIT, card_id=check["card_id"])]
        if check and not check.get("confirmed_once"):
            # Unclear: once more, in other words, as a plain yes / no. A second unclear answer
            # goes on with the conversation (`respond` drops the check).
            return [Step(ReplyIntent.REQUIREMENT_CONFIRM, card_id=check["card_id"])]
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
    elif state.get("turn_refine_search") and not relaxed:
        # Even after the options were shown: the search runs again with the new answers.
        steps.append(Step(ReplyIntent.PRESENT_OPTIONS, refine=True))
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


def clean_name(value: str | None) -> str | None:
    """A name as it may be stored and repeated to the lead: letters, spaces, apostrophes
    and hyphens, at most MAX_NAME_LENGTH characters and MAX_NAME_WORDS words, and nothing
    that reads as an instruction. Anything else is not a name (the agent asks again)."""
    text = _clean(normalize_inbound(value or ""), MAX_NAME_LENGTH)
    if text is None or not _NAME.fullmatch(text) or len(text.split()) > MAX_NAME_WORDS:
        return None
    return None if suspicion_flags(text) else text


def clean_text_answer(value: Any) -> str | None:
    """A free-text answer (a zone): short, without links or role markers."""
    if not isinstance(value, str):
        return None
    text = _clean(normalize_inbound(value), MAX_TEXT_ANSWER)
    if text is None or find_urls(text) or suspicion_flags(text) - {"url"}:
        return None
    return text


def _text_keys(questions: Sequence[QualificationQuestion]) -> set[str]:
    return {q.key for q in questions if q.kind is QuestionKind.TEXT}


def _checked_answer(question: QualificationQuestion, raw: Any) -> Any:
    value = parse_answer(question, raw)
    if value is not None and question.kind is QuestionKind.TEXT:
        return clean_text_answer(value)
    return value


def guard_input(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    """The message as the agent reads it (normalised), its suspicious patterns (logged as
    codes, never blocked), and stored values checked again with today's rules (a checkpoint
    from before them may hold a longer name or a zone with a link)."""
    context = runtime.context
    context.execution.stage = "guard_input"
    inbound = normalize_inbound(state["inbound"]) or state["inbound"].strip()
    flags = sorted(suspicion_flags(state["inbound"]))
    if flags:
        logger.info(
            "injection_suspected",
            extra={"tenant_id": str(context.turn.business.tenant_id), "codes": flags},
        )
    update: dict[str, Any] = {"inbound": inbound, "turn_flags": flags}
    name = state.get("visitor_name")
    if name and clean_name(name) != name:
        update["visitor_name"] = clean_name(name)
    answers = state.get("answers") or {}
    texts = _text_keys(enabled_questions(context))
    stale = [key for key in texts if key in answers and clean_text_answer(answers[key]) is None]
    if stale:
        update["answers"] = {k: v for k, v in answers.items() if k not in stale}
    return update


def _only_allowed(update: dict[str, Any]) -> dict[str, Any]:
    """`extract` writes only EXTRACT_KEYS (a bug here is a test failure, never a new key)."""
    return {key: value for key, value in update.items() if key in EXTRACT_KEYS}


def known_answers(answers: Mapping[str, Any], enabled: set[str]) -> dict[str, Any]:
    """The search answers the lead may change, as read-only context for the model."""
    return {key: answers[key] for key in REFINABLE_KEYS if key in enabled and key in answers}


def _deterministic(
    state: LeadState, context: GraphContext, offered: Sequence[Choice]
) -> Extraction:
    """What can be read without the model: a tapped choice and a plain yes / no (the
    opt-out matcher ran before)."""
    return Extraction(choice_id=selected_choice(context.turn.choice_id, None, offered))


def extract(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    return _only_allowed(_extract(state, runtime))


def _extract(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    context = runtime.context
    context.execution.stage = "extract"
    turn = context.turn
    if is_opt_out(state["inbound"]):
        # A clear "BAJA": no model call, nothing else is read from this message.
        return {"turn_opt_out": True}
    if state.get("hand_off_reason") == HandOffReason.HUMAN:
        return {}
    answers = dict(state.get("answers") or {})
    handed_off = bool(state.get("hand_off_reason"))
    offered = offered_choices(state)
    if handed_off and state.get("after_hand_off_replied_at"):
        # Later messages after a hand-off: no model call (only a tapped slot counts).
        return {"turn_choice": selected_choice(turn.choice_id, None, offered)}
    all_questions = enabled_questions(context)
    enabled = {q.key for q in all_questions}
    questions = applicable_questions(all_questions, answers)
    pending = [] if handed_off else [q for q in questions if q.key not in answers]
    # The lead's situation is read from every message, asked or not (never guessed).
    facts = (
        []
        if handed_off
        else [q for q in facts_for(_operation(answers.get("operation"))) if q.key not in answers]
    )
    asked_key = state.get("asked_key") or ""
    confirmation = CONFIRMATIONS.get(asked_key) or (
        OFFER_HUMAN_QUESTION if asked_key == QUIERE_PERSONA else None
    )
    update: dict[str, Any] = {}
    # The channel may already know how to reach the visitor (WhatsApp: their own number),
    # so the agent never asks for it.
    if not state.get("contact") and turn.visitor_contact:
        update["contact"] = turn.visitor_contact
    wants_name = not handed_off and not state.get("visitor_name")
    wants_contact = not handed_off and not state.get("contact") and "contact" not in update
    referenced = _referenced_listing(state, runtime.context, update)
    refinable = {} if handed_off else known_answers(answers, enabled)

    try:
        result = context.llm.extract(
            ExtractionRequest(
                questions=[*pending, *facts, *([confirmation] if confirmation else [])],
                transcript=turn.transcript,
                latest=state["inbound"],
                asked_key=state.get("asked_key"),
                wants_name=wants_name,
                wants_contact=wants_contact,
                choices=offered,
                known_answers=refinable,
            )
        )
    except ExecutionStopped:
        result = _deterministic(state, context, offered)
    except LlmUnavailableError:
        if not turn.final_attempt:
            raise
        # The message's last attempt: no silence. Only deterministic signals are read and
        # the conversation goes to the team.
        context.execution.stop(TerminationReason.PROVIDER_UNAVAILABLE)
        result = _deterministic(state, context, offered)
        update["turn_agent_failure"] = True
    if result.wants_opt_out:
        return {"turn_opt_out": True}
    update["turn_choice"] = selected_choice(turn.choice_id, result.choice_id, offered)
    update["turn_wants_human"] = result.wants_human
    # A tapped button never asks anything.
    update["turn_needs_answer"] = result.needs_answer and turn.choice_id is None
    update["turn_topic"] = result.topic if update["turn_needs_answer"] else None
    if handed_off:
        return update

    for question in [*pending, *facts]:
        value = _checked_answer(question, result.values.get(question.key))
        if value is not None:
            answers[question.key] = value
    if _refine(answers, refinable, result.changed_answers, all_questions):
        update["turn_refine_search"] = True
    if confirmation is not None:
        said = parse_answer(confirmation, result.values.get(confirmation.key))
        if not isinstance(said, bool):
            # Common short answers ("si dale", "no puedo") never depend on the model.
            said = read_yes_no(state["inbound"])
        if confirmation.key == QUIERE_PERSONA:
            if said:
                update["turn_wants_human"] = True
        else:
            key = (
                "turn_can_meet" if confirmation.key == PUEDE_CUMPLIR else "turn_wants_alternatives"
            )
            update[key] = said
    if referenced is not None:
        _choose_referenced(update, answers, referenced, state)
    update["answers"] = answers
    # A message that picks a card or a slot is that pick, never a name or a contact.
    picked = update["turn_choice"] is not None
    if wants_name and not picked and (name := clean_name(result.visitor_name)):
        update["visitor_name"] = name
    if wants_contact and not picked and (raw := _clean(result.contact, MAX_CONTACT_LENGTH)):
        contact = context.tools.call(SAVE_CONTACT, SaveContactInput(raw))
        if contact:
            update["contact"] = contact
        else:
            update["turn_contact_invalid"] = True
    return update


def _refine(
    answers: dict[str, Any],
    known: Mapping[str, Any],
    changed: Mapping[str, Any],
    questions: Sequence[QualificationQuestion],
) -> bool:
    """A changed search answer is taken only for a known, enabled key, only when it is valid
    for its question and differs from what is stored."""
    by_key = {q.key: q for q in questions}
    refined = False
    for key, raw in changed.items():
        question = by_key.get(key)
        if key not in known or question is None:
            continue
        value = _checked_answer(question, raw)
        if value is None or value == answers.get(key):
            continue
        answers[key] = value
        refined = True
    return refined


def _referenced_listing(
    state: LeadState, context: GraphContext, update: dict[str, Any]
) -> Listing | None:
    """The first message: the website button's text (or a pasted listing link) and the
    published property it names, if any."""
    if state.get("turns", 0) or state.get("offered_cards"):
        return None
    web = read_web_reference(state["inbound"])
    if web is None:
        return None
    if web.from_button:
        update["lead_source"] = "web_button"
    if web.reference.is_empty:
        return None
    listing: Listing | None = context.tools.call(
        FIND_REFERENCED_PROPERTY,
        FindReferencedPropertyInput(context.turn.business.tenant_id, web.reference),
    )
    return listing


def _choose_referenced(
    update: dict[str, Any], answers: dict[str, Any], listing: Listing, state: LeadState
) -> None:
    """The named property is already chosen: offered as the only card, its operation and
    zone answered (they are the property's), and picked this turn."""
    card = _card_payload(PropertyMatch(listing, False))
    update["offered_cards"] = [offered_card(card, listing.conditions)]
    update["shown_property_ids"] = [*(state.get("shown_property_ids") or []), card["id"]]
    update["properties_presented"] = True
    update["referenced_card"] = card["id"]
    update["turn_choice"] = card["id"]
    answers.setdefault("operation", "alquiler" if listing.operation is Operation.RENT else "compra")
    answers.setdefault("zone", clean_text_answer(listing.zone) or "")
    if not answers["zone"]:
        answers.pop("zone")


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
        # Imported text (CSV, Tokko, a portal): sanitised before any prompt sees it.
        "title": sanitize_untrusted(item.title, MAX_PROPERTY_TEXT),
        "address": sanitize_untrusted(item.address, MAX_PROPERTY_TEXT),
        "operation": item.operation.value,
        "zone": sanitize_untrusted(item.zone, MAX_PROPERTY_TEXT),
        "price_label": price_label(item),
        "rooms": item.rooms,
        # Always the listing's own link (or the sample's local page); never generated.
        "link": item.link,
        "over_budget": match.over_budget,
        "is_sample": item.is_sample,
    }


def card_label(card: dict[str, Any]) -> str:
    title = sanitize_untrusted(card["title"], MAX_PROPERTY_TEXT)
    address = sanitize_untrusted(card["address"], MAX_PROPERTY_TEXT)
    return f"{title} · {address}"


def offered_card(card: dict[str, Any], conditions: PropertyConditions) -> dict[str, Any]:
    """A shown card as the state keeps it: what the lead may pick and ask about. Its strings
    are already sanitised (`_card_payload`)."""
    return {
        "id": card["id"],
        "label": card_label(card),
        "operation": card["operation"],
        # Effective conditions as shown: the inbox never recomputes them.
        "conditions": conditions.to_json(),
        "title": card["title"],
        "address": card["address"],
        "zone": card["zone"],
        "price_label": card["price_label"],
        "rooms": card["rooms"],
        "link": card["link"],
    }


def _note(conditions: PropertyConditions) -> str:
    return sanitize_untrusted(conditions.condiciones or "", MAX_CONDITIONS_NOTE)


_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos")


def hours_text(blocks: Sequence[ScheduleBlock]) -> str:
    """ "lunes a viernes de 9:00 a 18:00": the team's hours in words, for answers."""
    by_hours: dict[tuple[str, str], list[int]] = {}
    for block in blocks:
        hours = (f"{block.opens:%-H:%M}", f"{block.closes:%-H:%M}")
        by_hours.setdefault(hours, []).append(block.weekday)
    parts = []
    for (opens, closes), days in sorted(by_hours.items(), key=lambda item: min(item[1])):
        days = sorted(set(days))
        if len(days) > 2 and days == list(range(days[0], days[-1] + 1)):
            when = f"{_WEEKDAYS[days[0]]} a {_WEEKDAYS[days[-1]]}"
        else:
            names = [_WEEKDAYS[day] for day in days]
            when = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]
        parts.append(f"{when} de {opens} a {closes}")
    return "; ".join(parts)


def answer_data(
    cards: Sequence[dict[str, Any]], answers: dict[str, Any], context: GraphContext
) -> dict[str, Any]:
    """The only data ANSWER_QUESTION may use: the options shown, in order, and the agency.
    Every imported string is sanitised; nothing here is ever an instruction."""
    turn = context.turn
    business = turn.business
    options = []
    for position, card in enumerate(cards, start=1):
        conditions = _card_conditions(card)
        match = card_match(card, answers)
        options.append(
            {
                "posicion": position,
                "titulo": card.get("title") or card.get("label"),
                "direccion": card.get("address"),
                "zona": card.get("zone"),
                "operacion": card.get("operation"),
                "precio": card.get("price_label"),
                "ambientes": card.get("rooms"),
                "link": card.get("link"),
                "condiciones": condition_phrases(conditions),
                "nota": _note(conditions) or None,
                "le_sirve": list(match.features),
                "pide": [failure.asks for failure in match.failed],
            }
        )
    return {
        "opciones": options,
        "inmobiliaria": {
            "nombre": business.business_name,
            "horario": hours_text(business.team_hours) or None,
            "abierto_ahora": is_within_hours(business.team_hours, business.timezone, turn.now)
            if business.team_hours
            else False,
        },
    }


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
            "outbox": [{"text": OPT_OUT_CONFIRMATION, "payload": None, "fixed": True}],
            "opt_out": True,
            "turn_opt_out": False,
            "asked_key": None,
            "turns": state.get("turns", 0) + 1,
        }
    context = runtime.context
    context.execution.stage = "respond"
    turn = context.turn
    config = turn.agent_config
    questions = enabled_questions(context)
    answers: dict[str, Any] = dict(state.get("answers") or {})
    policy: ConditionPolicy = context.tools.call(
        CONDITION_POLICY, ConditionPolicyInput(turn.business.tenant_id)
    )
    steps = plan_turn(state, questions, policy)
    update: dict[str, Any] = {}
    check = state.get("requirement_check")
    if (
        check
        and check.get("confirmed_once")
        and state.get("turn_can_meet") is None
        and not any(step.card_id == check["card_id"] for step in steps)
    ):
        # Asked twice, still unclear: never a third time; the team sees the mismatch.
        update["requirement_check"] = None
    facts: dict[str, str] = {"visitor_name": state.get("visitor_name") or ""}
    events: list[dict[str, Any]] = list(state.get("condition_events") or [])
    chosen: list[str] = list(state.get("chosen_property_ids") or [])

    execution = context.execution
    failed = False

    def fixed(step: Step) -> str:
        values = {
            **facts,
            "agent": config.agent_name,
            "business": turn.business.business_name,
            "question": step.question.label if step.question else "",
        }
        return safe_text(step.intent, values, hand_off=bool(facts.get("hand_off")))

    def reply(step: Step, data: Mapping[str, Any] | None = None) -> tuple[str, bool]:
        """The model's wording, or the fixed text once the turn stopped (a limit) or the
        model is down on the message's last attempt. True when the text is fixed."""
        nonlocal failed
        if execution.is_stopped or failed:
            return fixed(step), True
        try:
            text = context.llm.compose_reply(
                ReplyRequest(
                    intent=step.intent,
                    tone=config.tone,
                    agent_name=config.agent_name,
                    business_name=turn.business.business_name,
                    question=step.question,
                    facts={key: value for key, value in facts.items() if value},
                    lead_message=state["inbound"] if data is not None else None,
                    data=data or {},
                )
            ).text
        except ExecutionStopped:
            return fixed(step), True
        except LlmUnavailableError:
            if not turn.final_attempt:
                raise
            execution.stop(TerminationReason.PROVIDER_UNAVAILABLE)
            failed = True
            return fixed(step), True
        return text, False

    def message(step: Step, payload: dict[str, Any] | None = None, **extra: Any) -> None:
        text, is_fixed = reply(step, extra.pop("data", None))
        outbox.append(
            {
                "text": text,
                "payload": payload,
                "intent": step.intent.value,
                "fixed": is_fixed,
                # What the output guard sends instead if this text fails its checks.
                "safe": fixed(step),
            }
        )

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
    offers_human = any(step.intent is ReplyIntent.OFFER_HUMAN for step in steps)
    replied_at = state.get("after_hand_off_replied_at")
    for index, step in enumerate(steps):
        # Facts belong to their own step: a slot noted in this turn must not leak into the
        # hand-off message that follows it.
        facts = {"visitor_name": state.get("visitor_name") or ""}
        payload: dict[str, Any] | None = None
        intent = step.intent
        relax: dict[str, Any] | None = None

        if intent is ReplyIntent.GREET:
            named = card_of(state.get("referenced_card"))
            if named is not None:
                # The website button: the property they asked about, already chosen.
                facts["interested_in"] = named["label"]
            else:
                facts["looking_for"] = looking_for_fact(answers)

        elif intent is ReplyIntent.ASK and step.card_id is not None:
            # The decisive question of the chosen property: its slots come after the answer.
            assert step.question is not None
            choose(step.card_id)
            update["pending_card"] = step.card_id
            previous = state.get("gate_asked") if state.get("pending_card") == step.card_id else []
            update["gate_asked"] = [*(previous or []), step.question.key]

        elif intent is ReplyIntent.ANSWER_QUESTION:
            # Only from the options shown and the agency; it asks nothing.
            cards = update.get("offered_cards") or state.get("offered_cards") or []
            outbox.append(
                {
                    **_answer_message(reply, step, answer_data(cards, answers, context)),
                    "payload": None,
                }
            )
            if state.get("hand_off_reason"):
                update["after_hand_off_replied_at"] = turn.now.isoformat()
            continue

        elif intent is ReplyIntent.AFTER_HAND_OFF:
            # The first reply after the hand-off is worded as always; later ones are one
            # fixed text at most every AFTER_HAND_OFF_QUIET_HOURS, without the model; other
            # messages are only stored (the team sees them in the inbox).
            if replied_at is None:
                message(step)
            elif turn.now - datetime.fromisoformat(replied_at) >= timedelta(
                hours=AFTER_HAND_OFF_QUIET_HOURS
            ):
                outbox.append(
                    {"text": fixed(step), "payload": None, "intent": intent.value, "fixed": True}
                )
            else:
                continue
            update["after_hand_off_replied_at"] = turn.now.isoformat()
            continue

        elif intent is ReplyIntent.OFFER_HUMAN:
            update["stall_offered"] = True
            execution.finish(TerminationReason.CONVERSATION_STALLED)

        elif intent is ReplyIntent.PRESENT_OPTIONS:
            if step.again:
                offer = state.get("relax_offer") or {}
                if offer.get("requirement"):
                    accept(offer["requirement"])
                update["relax_offer"] = None
            if step.refine:
                # A changed search: what was pending about the old options is dropped; what
                # was already told (requirements, shown ids) is kept.
                update["relax_offer"] = None
                update["requirement_check"] = None
                update["pending_card"] = None
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
                    offered_card(card, match.listing.conditions)
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
                    and not offers_human
                ):
                    relax = {"requirement": failure.requirement.value, "asks": failure.asks}

        elif intent is ReplyIntent.REQUIREMENT_CHECK:
            card = card_of(step.card_id)
            assert card is not None and step.failure is not None
            choose(card["id"])
            update["pending_card"] = None
            update["requirement_check"] = {"card_id": card["id"], **step.failure}
            told = list(update.get("requirements_asked") or state.get("requirements_asked") or [])
            update["requirements_asked"] = [
                *told,
                requirement_key(card["id"], step.failure["requirement"]),
            ]
            events.append(_event("mismatch", card["id"]))
            facts["option"] = card["label"]
            facts["requirement"] = step.failure["asks"]
            note = _note(_card_conditions(card))
            if note:
                facts["conditions_note"] = note

        elif intent is ReplyIntent.REQUIREMENT_CONFIRM:
            check = state.get("requirement_check") or {}
            card = card_of(check.get("card_id"))
            assert card is not None
            update["requirement_check"] = {**check, "confirmed_once": True}
            facts["option"] = card["label"]
            facts["requirement"] = check["asks"]

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
                note = _note(_card_conditions(card))
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
            reason = _hand_off_reason(state, update, step)
            if step.stall:
                execution.finish(TerminationReason(step.stall))
            result: HandOffResult = context.tools.call(HAND_OFF, HandOffInput(reason))
            update["hand_off_reason"] = result.reason.value
            if reason is HandOffReason.AGENT_FAILURE:
                execution.finish(TerminationReason.AGENT_FAILURE)
                outbox.append(
                    {
                        "text": AGENT_FAILURE_TEXT,
                        "payload": None,
                        "intent": intent.value,
                        "fixed": True,
                    }
                )
            elif not (index > 0 and _folds_hand_off(steps, index - 1)):
                message(Step(intent))
            outbox.append({"text": result.event, "payload": None, "author": "system"})
            continue

        message(Step(intent, step.question), payload)
        if relax is not None:
            # Every option fails on the same requirement: ask about it once, and nothing else
            # this turn.
            update["relax_offer"] = relax
            update["relax_asked"] = True
            facts = {
                "visitor_name": state.get("visitor_name") or "",
                "requirement": plural(relax["asks"]),
            }
            message(Step(ReplyIntent.ASK_RELAX))
            asked_key = VER_ALTERNATIVAS
            break
        if step.question is not None:
            asked_key = step.question.key
        elif intent is ReplyIntent.OFFER_HUMAN:
            asked_key = QUIERE_PERSONA
        elif intent is ReplyIntent.ASK_NAME:
            asked_key = NAME_KEY
        elif intent in (ReplyIntent.ASK_CONTACT, ReplyIntent.INVALID_CONTACT):
            asked_key = CONTACT_KEY
        elif intent in (ReplyIntent.REQUIREMENT_CHECK, ReplyIntent.REQUIREMENT_CONFIRM):
            asked_key = PUEDE_CUMPLIR

    if failed and not update.get("hand_off_reason") and not state.get("hand_off_reason"):
        # The model went down mid-turn on the last attempt: what was said is fixed text, and
        # the team takes the conversation from here.
        result = context.tools.call(HAND_OFF, HandOffInput(HandOffReason.AGENT_FAILURE))
        update["hand_off_reason"] = result.reason.value
        execution.finish(TerminationReason.AGENT_FAILURE)
        outbox.append(
            {
                "text": AGENT_FAILURE_TEXT,
                "payload": None,
                "intent": ReplyIntent.HAND_OFF.value,
                "fixed": True,
            }
        )
        outbox.append({"text": result.event, "payload": None, "author": "system"})
        asked_key = None

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
        "turn_agent_failure": False,
        "property_matches": matches,
        "chosen_property_ids": chosen,
        "condition_events": events,
    }


def _hand_off_reason(state: LeadState, update: dict[str, Any], step: Step) -> HandOffReason:
    if step.reason is not None:
        return step.reason
    if state.get("turn_wants_human"):
        return HandOffReason.HUMAN
    if update.get("visit") or state.get("visit"):
        return HandOffReason.VISIT
    return HandOffReason.QUALIFIED


def _answer_message(reply: Any, step: Step, data: dict[str, Any]) -> dict[str, Any]:
    text, is_fixed = reply(step, data)
    return {"text": text, "intent": step.intent.value, "fixed": is_fixed, "data": data}


# --- Output guard -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CheckedText:
    text: str
    # A code when the text was replaced ("too_long", "contact", "income", "question",
    # "ungrounded", "empty"); None when it passed (links may have been removed).
    blocked: str | None = None


_SAMPLE_LINK = re.compile(r"^/ejemplo/")


def allowed_links(state: Mapping[str, Any], outbox: Sequence[Mapping[str, Any]]) -> set[str]:
    """Links a reply may contain: the shown cards' own links (or the sample pages)."""
    links = {str(card.get("link")) for card in state.get("offered_cards") or [] if card.get("link")}
    for item in outbox:
        for card in (item.get("payload") or {}).get("cards") or []:
            if card.get("link"):
                links.add(str(card["link"]))
    return {link.rstrip("/") for link in links}


def check_text(
    text: str,
    intent: ReplyIntent,
    allowed: set[str],
    data: Mapping[str, Any] | None = None,
) -> CheckedText:
    """One outbound text against the output rules (deterministic, every mode)."""
    if len(text) > MAX_REPLY_LENGTH:
        return CheckedText(text, "too_long")
    for url in find_urls(text):
        if url.rstrip("/") not in allowed and not _SAMPLE_LINK.match(url):
            text = text.replace(url, "").replace("  ", " ")
    text = text.strip()
    if not text:
        return CheckedText(text, "empty")
    if find_contacts(text):
        return CheckedText(text, "contact")
    if mentions_income(text):
        return CheckedText(text, "income")
    if intent is ReplyIntent.ANSWER_QUESTION:
        if "?" in text or "¿" in text:
            return CheckedText(text, "question")
        grounded = find_amounts(_flatten(data or {}))
        if not find_amounts(text) <= grounded:
            return CheckedText(text, "ungrounded")
    return CheckedText(text)


def _flatten(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, list | tuple):
        return " ".join(_flatten(item) for item in value)
    return "" if value is None else str(value)


def is_deferred(text: str) -> bool:
    return "lo consulto con el equipo" in normalize(text)


# Per-turn keys, reset when the turn ends.
TURN_KEYS = ("turn_flags", "turn_needs_answer", "turn_topic", "turn_refine_search")


def guard_output(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    """Every agent text this turn goes out only if it passes `check_text`; a failing one is
    replaced by its fixed text (an answer by the "lo consulto" text). Then the turn's
    outcome: answers given or deferred, progress, and the per-turn keys reset."""
    context = runtime.context
    execution = context.execution
    execution.stage = "guard_output"
    allowed = allowed_links(state, state.get("outbox") or [])
    outbox: list[dict[str, Any]] = []
    given = int(state.get("answers_given") or 0)
    deferred = int(state.get("answers_deferred") or 0)
    answered = False
    for item in state.get("outbox") or []:
        item = dict(item)
        data = item.pop("data", None)
        if item.get("author") == "system" or not item.get("intent"):
            outbox.append(item)
            continue
        intent = ReplyIntent(item["intent"])
        checked = check_text(item["text"], intent, allowed, data)
        text = checked.text
        if checked.blocked:
            execution.guard_blocks += 1
            code = "answer_ungrounded" if checked.blocked == "ungrounded" else "reply_guard_blocked"
            logger.warning(
                code,
                extra={
                    "tenant_id": str(context.turn.business.tenant_id),
                    "intent": intent.value,
                    "code": checked.blocked,
                },
            )
            text = (
                DEFERRED_ANSWER
                if intent is ReplyIntent.ANSWER_QUESTION
                else str(item.get("safe") or safe_text(intent))
            )
            if intent is not ReplyIntent.ANSWER_QUESTION:
                execution.finish(TerminationReason.GUARD_BLOCKED)
        if intent is ReplyIntent.ANSWER_QUESTION:
            if checked.blocked or is_deferred(text):
                deferred += 1
            else:
                given += 1
                answered = True
        item.pop("safe", None)
        outbox.append({**item, "text": text})
    after = {**state, "outbox": outbox}
    sent = [
        item["intent"] for item in outbox if item.get("author") != "system" and item.get("intent")
    ]
    progress = advance(
        state,
        after,
        refined=bool(state.get("turn_refine_search")),
        answered=answered,
        sent_intent=sent[-1] if sent else None,
    )
    return {
        "outbox": outbox,
        "answers_given": given,
        "answers_deferred": deferred,
        "progress": progress.to_json(),
        "termination_reason": execution.termination_reason.value,
        **{
            key: None if key == "turn_topic" else ([] if key == "turn_flags" else False)
            for key in TURN_KEYS
        },
    }


def build_lead_graph() -> StateGraph[Any, Any, Any, Any]:
    graph = StateGraph(LeadState, context_schema=GraphContext)
    graph.add_node("guard_input", guard_input)
    graph.add_node("extract", extract)
    graph.add_node("respond", respond)
    graph.add_node("guard_output", guard_output)
    graph.add_edge(START, "guard_input")
    graph.add_edge("guard_input", "extract")
    graph.add_edge("extract", "respond")
    graph.add_edge("respond", "guard_output")
    graph.add_edge("guard_output", END)
    return graph
