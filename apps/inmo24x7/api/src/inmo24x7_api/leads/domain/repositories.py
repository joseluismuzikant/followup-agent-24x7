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
