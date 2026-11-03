from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .lead import Lead, LeadStatus, Visit, VisitStatus


@dataclass(frozen=True, slots=True)
class LeadFilters:
    status: LeadStatus | None = None
    include_test: bool = False


@dataclass(frozen=True, slots=True)
class LeadPage:
    items: Sequence[Lead]
    total: int
    page: int
    page_size: int


class LeadRepository(Protocol):
    def get(self, tenant_id: UUID, lead_id: UUID) -> Lead | None: ...

    def get_by_thread(self, thread_id: UUID) -> Lead | None: ...

    def save(self, lead: Lead) -> None:
        """Insert or update, appending status history entries not stored yet."""
        ...

    def list(
        self, tenant_id: UUID, filters: LeadFilters, page: int, page_size: int
    ) -> LeadPage: ...

    def visits(self, lead_id: UUID) -> Sequence[Visit]: ...

    def add_visit(self, visit: Visit) -> None: ...

    def set_visit_status(self, visit_id: UUID, status: VisitStatus) -> None: ...

    def record_matches(
        self, lead_id: UUID, property_ids: Iterable[UUID], shown_at: datetime
    ) -> None:
        """Properties shown to the lead; already recorded ones keep their first shown_at."""
        ...
