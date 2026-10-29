"""The inmo24x7 basic qualification graph.

START -> extract -> respond -> END, once per inbound message.

The flow is decided here in code (`plan_turn`); the language model only reads values out of
the message (`extract`) and words each reply for an intent this module chose. Tone changes
wording, never the sequence of intents.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from followup_core.conversation.domain.answers import normalize, parse_answer
from followup_core.conversation.domain.llm import (
    CONTACT_KEY,
    NAME_KEY,
    ExtractionRequest,
    ReplyIntent,
    ReplyRequest,
)
from followup_core.conversation.infrastructure.langgraph_runtime import GraphContext
from followup_core.tenancy.domain.agent_config import QualificationQuestion
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langsmith import traceable

from .display import price_label
from .properties import Operation, PropertyQuery, PropertySearch

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
    asked_key: NotRequired[str | None]
    last_intent: NotRequired[str | None]
    turns: NotRequired[int]


@dataclass(frozen=True, slots=True)
class Step:
    intent: ReplyIntent
    question: QualificationQuestion | None = None


def enabled_questions(context: GraphContext) -> list[QualificationQuestion]:
    return [q for q in context.turn.agent_config.qualification_questions if q.enabled]


def plan_turn(state: LeadState, questions: Sequence[QualificationQuestion]) -> list[Step]:
    """The intents of this turn, in order. Each step becomes one outbound message, and only
    ASK/GREET steps carry a question, so a message never asks two things."""
    answers = state.get("answers") or {}
    first_turn = state.get("turns", 0) == 0
    if not first_turn and state.get("last_intent") in (ReplyIntent.CLOSE, ReplyIntent.AFTER_CLOSE):
        return [Step(ReplyIntent.AFTER_CLOSE)]

    pending = next((q for q in questions if q.key not in answers), None)
    enabled_keys = {q.key for q in questions}
    required = [key for key in REQUIRED_FILTERS if key in enabled_keys]
    filters_ready = all(key in answers for key in required) if required else pending is None

    steps: list[Step] = []
    if filters_ready and not state.get("properties_presented"):
        steps.append(Step(ReplyIntent.PRESENT_OPTIONS))
    if pending is not None:
        steps.append(Step(ReplyIntent.ASK, pending))
    elif not state.get("visitor_name"):
        steps.append(Step(ReplyIntent.ASK_NAME))
    elif not state.get("contact"):
        steps.append(Step(ReplyIntent.ASK_CONTACT))
    else:
        steps.append(Step(ReplyIntent.CLOSE))

    if first_turn:
        if steps[0].intent is ReplyIntent.ASK:
            steps[0] = Step(ReplyIntent.GREET, steps[0].question)
        else:
            steps.insert(0, Step(ReplyIntent.GREET))
    return steps


def _clean(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text if 0 < len(text) <= limit else None


def extract(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
    context = runtime.context
    answers = dict(state.get("answers") or {})
    pending = [q for q in enabled_questions(context) if q.key not in answers]
    wants_name = not state.get("visitor_name")
    wants_contact = not state.get("contact")
    if not pending and not wants_name and not wants_contact:
        return {}

    result = context.llm.extract(
        ExtractionRequest(
            questions=pending,
            transcript=context.turn.transcript,
            latest=state["inbound"],
            asked_key=state.get("asked_key"),
            wants_name=wants_name,
            wants_contact=wants_contact,
        )
    )
    for question in pending:
        value = parse_answer(question, result.values.get(question.key))
        if value is not None:
            answers[question.key] = value

    update: dict[str, Any] = {"answers": answers}
    if wants_name and (name := _clean(result.visitor_name, MAX_NAME_LENGTH)):
        update["visitor_name"] = name
    if wants_contact and (contact := _clean(result.contact, MAX_CONTACT_LENGTH)):
        update["contact"] = contact
    return update


def _operation(answer: Any) -> Operation | None:
    text = normalize(str(answer)) if answer is not None else ""
    if text.startswith("compr") or text.startswith("vent"):
        return "sale"
    if text.startswith("alquil"):
        return "rent"
    return None


def _query(answers: dict[str, Any], enabled_keys: set[str]) -> PropertyQuery:
    """Built-in filters only; custom_* answers never filter properties."""
    budget = answers.get("budget") if "budget" in enabled_keys else None
    rooms = answers.get("rooms") if "rooms" in enabled_keys else None
    return PropertyQuery(
        operation=_operation(answers.get("operation")),
        zone=answers.get("zone"),
        max_budget=budget["amount"] if budget else None,
        budget_currency=budget["currency"] if budget else None,
        rooms=rooms if isinstance(rooms, int) else None,
    )


def build_lead_graph(properties: PropertySearch) -> StateGraph[Any, Any, Any, Any]:
    # A child run of the turn when it is traced; a plain call otherwise.
    search_properties = traceable(name="property_search", run_type="tool")(properties.search)

    def respond(state: LeadState, runtime: Runtime[GraphContext]) -> dict[str, Any]:
        context = runtime.context
        config = context.turn.agent_config
        questions = enabled_questions(context)
        answers = state.get("answers") or {}
        steps = plan_turn(state, questions)

        def reply(step: Step) -> str:
            facts = {"visitor_name": state.get("visitor_name") or ""}
            return context.llm.compose_reply(
                ReplyRequest(
                    intent=step.intent,
                    tone=config.tone,
                    agent_name=config.agent_name,
                    business_name=context.turn.business.business_name,
                    question=step.question,
                    facts={key: value for key, value in facts.items() if value},
                )
            ).text

        outbox: list[dict[str, Any]] = []
        update: dict[str, Any] = {}
        asked_key: str | None = None
        for step in steps:
            if step.intent is ReplyIntent.PRESENT_OPTIONS:
                matches = search_properties(_query(answers, {q.key for q in questions}))
                update["properties_presented"] = True
                if not matches:
                    outbox.append({"text": reply(Step(ReplyIntent.NO_OPTIONS)), "payload": None})
                    continue
                cards = [
                    {
                        "id": match.property.id,
                        "title": match.property.title,
                        "address": match.property.address,
                        "operation": match.property.operation,
                        "zone": match.property.zone,
                        "price_label": price_label(match.property),
                        "rooms": match.property.rooms,
                        "link": match.property.link,
                        "over_budget": match.over_budget,
                        "is_sample": match.property.is_sample,
                    }
                    for match in matches
                ]
                outbox.append({"text": reply(step), "payload": {"cards": cards}})
                update["shown_property_ids"] = [
                    *(state.get("shown_property_ids") or []),
                    *(card["id"] for card in cards),
                ]
                continue

            outbox.append({"text": reply(step), "payload": None})
            if step.question is not None:
                asked_key = step.question.key
            elif step.intent is ReplyIntent.ASK_NAME:
                asked_key = NAME_KEY
            elif step.intent is ReplyIntent.ASK_CONTACT:
                asked_key = CONTACT_KEY

        return {
            **update,
            "outbox": outbox,
            "asked_key": asked_key,
            "last_intent": steps[-1].intent.value,
            "turns": state.get("turns", 0) + 1,
        }

    graph = StateGraph(LeadState, context_schema=GraphContext)
    graph.add_node("extract", extract)
    graph.add_node("respond", respond)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "respond")
    graph.add_edge("respond", END)
    return graph
