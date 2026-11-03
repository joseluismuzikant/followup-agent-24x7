"""Inicio (S5): this week's KPIs and "Para atender hoy"."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from followup_core.identity.domain.profile import Profile
from pydantic import BaseModel

from ..auth import current_profile
from ..leads.display import looking_for
from ..leads.router import LeadStatusName
from .application.get_dashboard import GetDashboard


class ReceivedRead(BaseModel):
    total: int
    # "N fuera de horario": the first message came outside team hours.
    out_of_hours: int


class VisitsKpiRead(BaseModel):
    # Proposed or confirmed this week, not cancelled.
    total: int
    confirmed: int


class TodayLeadRead(BaseModel):
    id: UUID
    # Name, else the phone or email; null when the agent has neither yet.
    name: str | None
    looking_for: str
    status: LeadStatusName
    created_at: datetime
    last_activity_at: datetime


class DashboardRead(BaseModel):
    business_name: str
    # Monday 00:00 in the business's timezone.
    week_start: datetime
    received: ReceivedRead
    # With zone and budget (the enabled ones among operation, zone and budget).
    qualified: int
    visits: VisitsKpiRead
    # Average seconds from a lead's message to the agent's first reply; null without data.
    response_time_seconds: float | None
    attention_today: list[TodayLeadRead]


def build_dashboard_router(dashboard_factory: Callable[..., GetDashboard]) -> APIRouter:
    router = APIRouter(tags=["dashboard"])

    @router.get("/dashboard", response_model=DashboardRead)
    def get_dashboard(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[GetDashboard, Depends(dashboard_factory)],
    ) -> DashboardRead:
        dashboard = use_case.execute(profile.tenant_id)
        return DashboardRead(
            business_name=dashboard.business_name,
            week_start=dashboard.week_start,
            received=ReceivedRead(total=dashboard.received, out_of_hours=dashboard.out_of_hours),
            qualified=dashboard.qualified,
            visits=VisitsKpiRead(total=dashboard.visits, confirmed=dashboard.visits_confirmed),
            response_time_seconds=dashboard.response_seconds,
            attention_today=[
                TodayLeadRead(
                    id=lead.id,
                    name=lead.visitor_name or lead.contact,
                    looking_for=looking_for(lead.answers),
                    status=lead.status.value,
                    created_at=lead.created_at,
                    last_activity_at=lead.last_activity_at,
                )
                for lead in dashboard.attention_today
            ],
        )

    return router
