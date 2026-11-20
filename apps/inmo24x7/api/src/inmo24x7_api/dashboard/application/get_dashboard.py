from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from followup_core.conversation.application.ports import AgentConfigSource, BusinessContextSource
from followup_core.conversation.application.threads import Clock, utc_now

from ...leads.domain.lead import WEB_BUTTON, Lead
from ...leads.domain.repositories import InboxTab, LeadFilters, LeadRepository
from ..domain.kpis import (
    TranscriptRow,
    average,
    is_out_of_hours,
    is_qualified,
    qualifying_keys,
    response_times,
    week_start,
)

TODAY_ROWS = 5


@dataclass(frozen=True, slots=True)
class WeekLead:
    created_at: datetime
    answers: dict[str, Any]
    # "web_button" when it came from the website's WhatsApp button.
    source: str | None = None


class DashboardQueries(Protocol):
    """Rows for real leads only (never simulator tests)."""

    def leads_created_since(self, tenant_id: UUID, since: datetime) -> Sequence[WeekLead]: ...

    def visits_since(self, tenant_id: UUID, since: datetime) -> tuple[int, int]:
        """(proposed or confirmed, confirmed) among the visits created since `since`."""
        ...

    def transcript_since(self, tenant_id: UUID, since: datetime) -> Sequence[TranscriptRow]:
        """Messages of the threads active since `since`, by thread and position."""
        ...

    def recent_qualifying(self, tenant_id: UUID, limit: int) -> Sequence[Lead]: ...


@dataclass(frozen=True, slots=True)
class Dashboard:
    business_name: str
    week_start: datetime
    received: int
    out_of_hours: int
    qualified: int
    visits: int
    visits_confirmed: int
    response_seconds: float | None
    attention_today: Sequence[Lead]
    # Of `received`, how many came from the website's button ("Web — botón").
    from_web: int = 0
    # This month, in the business's timezone, from stored events (never estimated).
    month_start: datetime | None = None
    mismatches: int = 0
    visits_avoided: int = 0


def month_start(now: datetime, timezone: str) -> datetime:
    """The first day of this month at 00:00 in the business's timezone."""
    local = now.astimezone(ZoneInfo(timezone))
    return local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class GetDashboard:
    def __init__(
        self,
        queries: DashboardQueries,
        leads: LeadRepository,
        business: BusinessContextSource,
        configs: AgentConfigSource,
        clock: Clock = utc_now,
    ) -> None:
        self._queries = queries
        self._leads = leads
        self._business = business
        self._configs = configs
        self._clock = clock

    def execute(self, tenant_id: UUID) -> Dashboard:
        business = self._business(tenant_id)
        since = week_start(self._clock(), business.timezone)
        week = self._queries.leads_created_since(tenant_id, since)
        keys = qualifying_keys(self._configs.current(tenant_id)[1])
        visits, confirmed = self._queries.visits_since(tenant_id, since)
        month = month_start(self._clock(), business.timezone)
        counts = self._leads.condition_counts(tenant_id, month, self._clock())
        return Dashboard(
            business_name=business.business_name,
            week_start=since,
            received=len(week),
            out_of_hours=sum(
                is_out_of_hours(lead.created_at, business.team_hours, business.timezone)
                for lead in week
            ),
            qualified=sum(is_qualified(lead.answers, keys) for lead in week),
            from_web=sum(lead.source == WEB_BUTTON for lead in week),
            visits=visits,
            visits_confirmed=confirmed,
            response_seconds=average(
                response_times(self._queries.transcript_since(tenant_id, since), since)
            ),
            attention_today=self._today(tenant_id),
            month_start=month,
            mismatches=counts.mismatches,
            visits_avoided=counts.visits_avoided,
        )

    def _today(self, tenant_id: UUID) -> list[Lead]:
        """ "Para atender hoy": the most urgent leads, topped up with the newest still
        qualifying."""
        urgent = list(
            self._leads.list(tenant_id, LeadFilters(tab=InboxTab.ATTENTION), 1, TODAY_ROWS).items
        )
        if len(urgent) < TODAY_ROWS:
            urgent += self._queries.recent_qualifying(tenant_id, TODAY_ROWS - len(urgent))
        return urgent
