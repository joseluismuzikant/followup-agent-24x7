"""Consultas (minimal until the Day 6 inbox): the tenant's leads, newest activity first."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from followup_core.identity.domain.profile import Profile
from followup_core.messaging.domain.outbound import overall_status
from followup_core.messaging.domain.repositories import OutboundRepository
from pydantic import BaseModel

from ..auth import current_profile
from ..http_errors import ApiError
from ..simulator import KnownFactRead, MessageRead, message_read
from .application.queries import GetLead, ListLeads
from .display import known_rows, looking_for
from .domain.errors import LeadNotFoundError
from .domain.lead import Lead, LeadStatus
from .domain.repositories import LeadFilters

LeadStatusName = Literal["qualifying", "visit_proposed", "human_requested", "visit_confirmed"]
HandOffReasonName = Literal["human", "visit", "qualified"]


class LeadRead(BaseModel):
    id: UUID
    visitor_name: str | None
    contact: str | None
    # "Alquiler · 2 amb. · Palermo · hasta $900.000"
    looking_for: str
    status: LeadStatusName
    is_test: bool
    channel: str
    handed_off_at: datetime | None
    hand_off_reason: HandOffReasonName | None
    created_at: datetime
    last_activity_at: datetime


class LeadListRead(BaseModel):
    items: list[LeadRead]
    total: int
    page: int
    page_size: int


class StatusChangeRead(BaseModel):
    status: LeadStatusName
    changed_at: datetime


class VisitRead(BaseModel):
    id: UUID
    property_id: UUID | None
    property_label: str
    starts_at: datetime
    status: Literal["proposed", "confirmed", "cancelled"]


class LeadDetailRead(LeadRead):
    answers: list[KnownFactRead]
    status_history: list[StatusChangeRead]
    visits: list[VisitRead]
    transcript: list[MessageRead]


def lead_read(lead: Lead) -> LeadRead:
    return LeadRead(
        id=lead.id,
        visitor_name=lead.visitor_name,
        contact=lead.contact,
        looking_for=looking_for(lead.answers),
        status=lead.status.value,
        is_test=lead.is_test,
        channel=lead.channel,
        handed_off_at=lead.handed_off_at,
        hand_off_reason=lead.hand_off_reason.value if lead.hand_off_reason else None,
        created_at=lead.created_at,
        last_activity_at=lead.last_activity_at,
    )


def build_leads_router(
    list_factory: Callable[..., ListLeads],
    get_factory: Callable[..., GetLead],
    delivery_factory: Callable[..., OutboundRepository],
) -> APIRouter:
    router = APIRouter(tags=["leads"])

    @router.get("/leads", response_model=LeadListRead)
    def list_leads(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[ListLeads, Depends(list_factory)],
        status: LeadStatusName | None = None,
        include_test: bool = False,
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> LeadListRead:
        result = use_case.execute(
            profile.tenant_id,
            LeadFilters(status=LeadStatus(status) if status else None, include_test=include_test),
            page,
        )
        return LeadListRead(
            items=[lead_read(lead) for lead in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    @router.get("/leads/{lead_id}", response_model=LeadDetailRead)
    def get_lead(
        lead_id: UUID,
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[GetLead, Depends(get_factory)],
        delivery: Annotated[OutboundRepository, Depends(delivery_factory)],
    ) -> LeadDetailRead:
        try:
            detail = use_case.execute(profile.tenant_id, lead_id)
        except LeadNotFoundError as error:
            raise ApiError(404, "lead_not_found") from error
        lead = detail.lead
        statuses = delivery.statuses([message.id for message in detail.transcript])
        state = {
            "answers": lead.answers,
            "visitor_name": lead.visitor_name,
            "contact": lead.contact,
        }
        return LeadDetailRead(
            **lead_read(lead).model_dump(),
            answers=[
                KnownFactRead(key=row.key, label=row.label, value=row.value)
                for row in known_rows(detail.agent_config, state)
            ],
            status_history=[
                StatusChangeRead(status=change.status.value, changed_at=change.changed_at)
                for change in lead.history
            ],
            visits=[
                VisitRead(
                    id=visit.id,
                    property_id=visit.property_id,
                    property_label=visit.property_label,
                    starts_at=visit.starts_at,
                    status=visit.status.value,
                )
                for visit in detail.visits
            ],
            transcript=[
                message_read(message, delivery=overall_status(statuses.get(message.id, ())))
                for message in detail.transcript
            ],
        )

    return router
