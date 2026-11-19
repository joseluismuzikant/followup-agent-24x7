import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from followup_core.conversation.domain.answers import normalize
from followup_core.messaging.domain.phones import to_e164

from .lead import Lead, Visit, digits

_PHONE_LIKE = re.compile(r"^[\d\s()+.\-]+$")


class InboxTab(StrEnum):
    ATTENTION = "attention"  # Para atender: `Lead.needs_attention`, most urgent first
    VISITS = "visits"  # a proposed or confirmed visit, by visit time
    ALL = "all"  # by last activity


@dataclass(frozen=True, slots=True)
class Search:
    """The inbox search box: a phone in any format matches the stored digits; anything else
    matches name, zone and answers, accent-insensitive."""

    text: str | None = None
    digits: str | None = None

    @classmethod
    def parse(cls, query: str | None) -> "Search":
        raw = (query or "").strip()[:100]
        if not raw:
            return cls()
        if _PHONE_LIKE.fullmatch(raw) and len(digits(raw)) >= 4:
            e164 = to_e164(raw)
            return cls(digits=e164.lstrip("+") if e164 else digits(raw))
        return cls(text=normalize(raw))


@dataclass(frozen=True, slots=True)
class LeadFilters:
    tab: InboxTab = InboxTab.ALL
    search: Search = field(default_factory=Search)
    include_test: bool = False
    # cumple / no_cumple / sin_datos (the inbox's conditions filter).
    conditions: str | None = None


@dataclass(frozen=True, slots=True)
class Evaluation:
    """How a shown property compared with the lead, as the agent knew it."""

    property_id: UUID
    # Match.to_json(); None when nothing was evaluated yet.
    match: Mapping[str, object] | None
    chosen: bool = False


@dataclass(frozen=True, slots=True)
class StoredMatch:
    property_id: UUID
    title: str
    address: str
    match: Mapping[str, object] | None
    chosen: bool
    override_status: str | None
    evaluated_at: datetime | None

    @property
    def status(self) -> str | None:
        """The team's decision wins over the agent's evaluation."""
        if self.override_status:
            return self.override_status
        value = (self.match or {}).get("status")
        return str(value) if value else None


def lead_status(matches: Sequence[StoredMatch]) -> str | None:
    """The lead's overall status: over the properties they chose (or, without any, the ones
    shown): cumple if one fits, no_cumple if every one with data fails, else sin_datos."""
    chosen = [item for item in matches if item.chosen]
    pool = chosen or list(matches)
    statuses = [item.status for item in pool if item.status]
    if not statuses:
        return None
    if "cumple" in statuses:
        return "cumple"
    known = [status for status in statuses if status != "sin_datos"]
    if known and all(status == "no_cumple" for status in known):
        return "no_cumple"
    return "sin_datos"


@dataclass(frozen=True, slots=True)
class ConditionCounts:
    """Inicio's month: real leads that did not meet a chosen property's requirements, and
    visits avoided (the lead said they could not meet it before booking)."""

    mismatches: int = 0
    visits_avoided: int = 0


@dataclass(frozen=True, slots=True)
class LeadPage:
    items: Sequence[Lead]
    total: int
    page: int
    page_size: int
    # Leads per tab with the same search and test filter.
    counts: Mapping[InboxTab, int] = field(default_factory=dict)
    # The next proposed or confirmed visit of each listed lead.
    next_visits: Mapping[UUID, datetime] = field(default_factory=dict)


class LeadRepository(Protocol):
    def get(self, tenant_id: UUID, lead_id: UUID) -> Lead | None: ...

    def get_by_thread(self, thread_id: UUID) -> Lead | None: ...

    def get_by_thread_key(self, thread_key: str) -> Lead | None: ...

    def save(self, lead: Lead) -> None:
        """Insert or update, appending status history entries not stored yet."""
        ...

    def list(
        self, tenant_id: UUID, filters: LeadFilters, page: int, page_size: int
    ) -> LeadPage: ...

    def export(self, tenant_id: UUID, filters: LeadFilters, limit: int) -> Sequence[Lead]:
        """The same leads and order as `list`, without paging."""
        ...

    def visits(self, lead_id: UUID) -> Sequence[Visit]: ...

    def latest_visits(self, lead_ids: Sequence[UUID]) -> Mapping[UUID, Visit]:
        """The most recent visit of each lead, for the export."""
        ...

    def add_visit(self, visit: Visit) -> None: ...

    def save_visit(self, visit: Visit) -> None:
        """Updates status and time."""
        ...

    def record_matches(
        self, lead_id: UUID, property_ids: Iterable[UUID], shown_at: datetime
    ) -> None:
        """Properties shown to the lead; already recorded ones keep their first shown_at."""
        ...

    def record_evaluations(
        self, lead_id: UUID, evaluations: Sequence[Evaluation], at: datetime
    ) -> None:
        """Stores each shown property's match (and whether the lead chose it); the team's
        override is kept."""
        ...

    def matches(self, lead_id: UUID) -> Sequence[StoredMatch]: ...

    def refresh_conditions_status(self, lead_id: UUID) -> str | None:
        """Recomputes and stores the lead's overall status (`lead_status`)."""
        ...

    def override_match(
        self, lead_id: UUID, property_id: UUID, status: str | None, profile_id: UUID, at: datetime
    ) -> bool:
        """ "Cumple igual" (or back to the agent's evaluation with None). False when the
        property was never shown to the lead."""
        ...

    def record_condition_events(
        self,
        tenant_id: UUID,
        lead_id: UUID,
        events: Sequence[tuple[str, UUID | None]],
        at: datetime,
    ) -> None:
        """ "mismatch" / "visit_avoided" / "no_fit", each once per lead and property."""
        ...

    def condition_counts(
        self, tenant_id: UUID, start: datetime, end: datetime
    ) -> ConditionCounts: ...
