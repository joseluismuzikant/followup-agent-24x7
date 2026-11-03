"""The lead agent's tools, declared once.

Every tool has an input schema (a frozen dataclass) and a handler. Handlers only read or
compute: the graph keeps their results in its state and `RecordLeadTurn` writes the lead,
the visit and the hand-off in the turn's transaction. Each call is a child run of the traced
turn named after the tool.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from followup_core.conversation.domain.tools import Tool, ToolRegistry
from followup_core.tenancy.domain.business_settings import ScheduleBlock, is_within_hours

from ..properties.domain.search import PropertyMatch, PropertyQuery, PropertySearch
from .domain.contact import normalize_contact
from .domain.lead import HandOffReason
from .domain.slots import propose_slots, short_slot_label, slot_label

SEARCH_PROPERTIES = "search_properties"
SAVE_CONTACT = "save_contact"
PROPOSE_VISIT = "propose_visit"
HAND_OFF = "hand_off"

HAND_OFF_EVENT = "El agente derivó la consulta a tu equipo"


@dataclass(frozen=True, slots=True)
class SearchPropertiesInput:
    tenant_id: UUID
    query: PropertyQuery


@dataclass(frozen=True, slots=True)
class SaveContactInput:
    text: str


@dataclass(frozen=True, slots=True)
class ProposeVisitInput:
    property_id: str
    property_label: str
    team_hours: tuple[ScheduleBlock, ...]
    timezone: str
    now: datetime


@dataclass(frozen=True, slots=True)
class VisitSlot:
    id: str  # unique per start time, so a slot of an older offer never matches a new one
    label: str
    short_label: str  # "jue 6/11 10:30", fits a WhatsApp reply button
    starts_at: str  # ISO 8601 with the tenant's offset


@dataclass(frozen=True, slots=True)
class VisitProposal:
    property_id: str
    property_label: str
    slots: Sequence[VisitSlot]
    # Proposed outside team hours: the reply says the team confirms when it is back.
    after_hours: bool


@dataclass(frozen=True, slots=True)
class HandOffInput:
    reason: HandOffReason


@dataclass(frozen=True, slots=True)
class HandOffResult:
    reason: HandOffReason
    event: str  # the system message added to the transcript


DECLARED: Mapping[str, tuple[str, type[Any]]] = {
    SEARCH_PROPERTIES: (
        "Published properties of the tenant matching the lead's answers.",
        SearchPropertiesInput,
    ),
    SAVE_CONTACT: (
        "Validates and normalizes a phone (+54 9 ...) or an email.",
        SaveContactInput,
    ),
    PROPOSE_VISIT: (
        "The next two 30-minute visit slots inside team hours, at least 2 hours ahead.",
        ProposeVisitInput,
    ),
    HAND_OFF: (
        "Passes the conversation to the team and records the system event.",
        HandOffInput,
    ),
}


def _propose_visit(arguments: ProposeVisitInput) -> VisitProposal:
    starts = propose_slots(arguments.team_hours, arguments.timezone, arguments.now)
    return VisitProposal(
        property_id=arguments.property_id,
        property_label=arguments.property_label,
        slots=[
            VisitSlot(
                id=f"slot-{start:%Y%m%d%H%M}",
                label=slot_label(start),
                short_label=short_slot_label(start),
                starts_at=start.isoformat(),
            )
            for start in starts
        ],
        after_hours=not is_within_hours(arguments.team_hours, arguments.timezone, arguments.now),
    )


def _hand_off(arguments: HandOffInput) -> HandOffResult:
    return HandOffResult(reason=arguments.reason, event=HAND_OFF_EVENT)


def lead_handlers(search: PropertySearch) -> Mapping[str, Callable[[Any], Any]]:
    def search_properties(arguments: SearchPropertiesInput) -> Sequence[PropertyMatch]:
        return search.search(arguments.tenant_id, arguments.query)

    def save_contact(arguments: SaveContactInput) -> str | None:
        return normalize_contact(arguments.text)

    return {
        SEARCH_PROPERTIES: search_properties,
        SAVE_CONTACT: save_contact,
        PROPOSE_VISIT: _propose_visit,
        HAND_OFF: _hand_off,
    }


def lead_tools(search: PropertySearch) -> ToolRegistry:
    handlers = lead_handlers(search)
    if set(handlers) != set(DECLARED):
        raise RuntimeError(
            f"Tools without a handler or declaration: {set(handlers) ^ set(DECLARED)}"
        )
    return ToolRegistry(
        Tool(name, description, input_type, handlers[name])
        for name, (description, input_type) in DECLARED.items()
    )
