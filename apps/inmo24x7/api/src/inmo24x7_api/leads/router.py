"""Consultas (S6): the inbox tabs, search and CSV export, the lead detail, and the team's
actions (take over, reply, give back, confirm or cancel the visit)."""

import csv
import io
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from followup_core.conversation.application.control import Actor
from followup_core.conversation.domain.errors import (
    ConversationNotTakenError,
    InvalidMessageError,
)
from followup_core.conversation.domain.thread import Channel
from followup_core.identity.domain.profile import Profile, Role
from followup_core.messaging.domain.outbound import overall_status
from followup_core.messaging.domain.repositories import OutboundRepository
from pydantic import BaseModel, Field

from ..auth import current_profile, require_role
from ..http_errors import ApiError
from ..simulator import KnownFactRead, MessageRead, message_read
from .application.inbox import LeadActions, service_window
from .application.queries import ExportLeads, GetLead, LeadDetail, ListLeads
from .display import known_rows, lead_csv, looking_for
from .domain.errors import (
    InvalidLeadTransitionError,
    LeadNotFoundError,
    OutsideServiceWindowError,
    TemplateNotConfiguredError,
    VisitCancelledError,
    VisitNotFoundError,
    VisitTimeInPastError,
)
from .domain.lead import Lead
from .domain.repositories import InboxTab, LeadFilters, Search

logger = logging.getLogger("inmo24x7.leads")

LeadStatusName = Literal["qualifying", "visit_proposed", "human_requested", "visit_confirmed"]
HandOffReasonName = Literal["human", "visit", "qualified"]
TabName = Literal["attention", "visits", "all"]
MAX_TEAM_MESSAGE = 4096

# Owner, manager and agent act on leads; a viewer only reads.
can_act = require_role(Role.OWNER, Role.MANAGER, Role.AGENT)


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
    # The "Para atender" rule (Lead.needs_attention).
    needs_attention: bool = False
    # The next proposed or confirmed visit (list only).
    next_visit_at: datetime | None = None


class TabCountsRead(BaseModel):
    attention: int
    visits: int
    all: int


class LeadListRead(BaseModel):
    items: list[LeadRead]
    total: int
    page: int
    page_size: int
    counts: TabCountsRead


class StatusChangeRead(BaseModel):
    status: LeadStatusName
    changed_at: datetime


class VisitRead(BaseModel):
    id: UUID
    property_id: UUID | None
    property_label: str
    starts_at: datetime
    status: Literal["proposed", "confirmed", "cancelled"]


class PersonRead(BaseModel):
    id: UUID
    name: str


class ControlRead(BaseModel):
    mode: Literal["agent", "human"]
    # Who on the team has the conversation (mode "human").
    by: PersonRead | None
    changed_at: datetime | None


class ServiceWindowRead(BaseModel):
    """WhatsApp's 24 hours to write freely after the lead's last message."""

    open: bool
    expires_at: datetime | None


class LeadDetailRead(LeadRead):
    answers: list[KnownFactRead]
    status_history: list[StatusChangeRead]
    visits: list[VisitRead]
    transcript: list[MessageRead]
    control: ControlRead
    # WhatsApp only.
    service_window: ServiceWindowRead | None


class TeamMessageWrite(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEAM_MESSAGE)


class ConfirmVisitWrite(BaseModel):
    # Another time for the visit; must be in the future.
    starts_at: datetime | None = None


class CancelVisitWrite(BaseModel):
    # Optional message to the lead (free text: inside the WhatsApp window only).
    message: str | None = Field(default=None, max_length=MAX_TEAM_MESSAGE)


def lead_read(lead: Lead, next_visit_at: datetime | None = None) -> LeadRead:
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
        needs_attention=lead.needs_attention,
        next_visit_at=next_visit_at,
    )


def actor(profile: Profile) -> Actor:
    """How the transcript names the person: display name, else the email."""
    return Actor(profile.id, profile.display_name.strip() or profile.email)


def _filters(tab: TabName, q: str | None, include_test: bool) -> LeadFilters:
    return LeadFilters(tab=InboxTab(tab), search=Search.parse(q), include_test=include_test)


def detail_read(
    detail: LeadDetail, delivery: OutboundRepository, now: datetime | None = None
) -> LeadDetailRead:
    lead, thread = detail.lead, detail.thread
    statuses = delivery.statuses([message.id for message in detail.transcript])
    state = {"answers": lead.answers, "visitor_name": lead.visitor_name, "contact": lead.contact}
    window = None
    if thread is not None and thread.channel is Channel.WHATSAPP:
        current = service_window(detail.transcript)
        window = ServiceWindowRead(
            open=current.is_open(now or datetime.now(UTC)), expires_at=current.expires_at
        )
    controller = thread.controlled_by_profile_id if thread else None
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
            message_read(
                message,
                delivery=overall_status(statuses.get(message.id, ())),
                author_name=detail.names.get(message.author_profile_id)
                if message.author_profile_id
                else None,
            )
            for message in detail.transcript
        ],
        control=ControlRead(
            mode=thread.control.value if thread else "agent",  # type: ignore[arg-type]
            by=PersonRead(id=controller, name=detail.names.get(controller, "Alguien del equipo"))
            if controller
            else None,
            changed_at=thread.control_changed_at if thread else None,
        ),
        service_window=window,
    )


def build_leads_router(
    list_factory: Callable[..., ListLeads],
    get_factory: Callable[..., GetLead],
    delivery_factory: Callable[..., OutboundRepository],
    export_factory: Callable[..., ExportLeads],
    actions_factory: Callable[..., LeadActions],
) -> APIRouter:
    router = APIRouter(tags=["leads"])

    @router.get("/leads", response_model=LeadListRead)
    def list_leads(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[ListLeads, Depends(list_factory)],
        tab: TabName = "all",
        q: Annotated[str | None, Query(max_length=100)] = None,
        include_test: bool = False,
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> LeadListRead:
        result = use_case.execute(profile.tenant_id, _filters(tab, q, include_test), page)
        return LeadListRead(
            items=[lead_read(lead, result.next_visits.get(lead.id)) for lead in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
            counts=TabCountsRead(
                attention=result.counts.get(InboxTab.ATTENTION, 0),
                visits=result.counts.get(InboxTab.VISITS, 0),
                all=result.counts.get(InboxTab.ALL, 0),
            ),
        )

    # Declared before /leads/{lead_id}, which would otherwise take "export.csv" as an id.
    @router.get(
        "/leads/export.csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def export_leads(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[ExportLeads, Depends(export_factory)],
        tab: TabName = "all",
        q: Annotated[str | None, Query(max_length=100)] = None,
        include_test: bool = False,
    ) -> Response:
        export = use_case.execute(profile.tenant_id, _filters(tab, q, include_test))
        buffer = io.StringIO()
        # Excel in es-AR expects ";" and needs the BOM to read UTF-8.
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        for row in lead_csv(export):
            writer.writerow(row)
        # Only the count: the rows are personal data.
        logger.info("leads_exported", extra={"rows": len(export.leads)})
        filename = f"consultas-{datetime.now(UTC):%Y-%m-%d}.csv"
        return Response(
            content="﻿" + buffer.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
        return detail_read(detail, delivery)

    def refreshed(
        lead_id: UUID, profile: Profile, get: GetLead, delivery: OutboundRepository
    ) -> LeadDetailRead:
        return detail_read(get.execute(profile.tenant_id, lead_id), delivery)

    @router.post("/leads/{lead_id}/takeover", response_model=LeadDetailRead)
    def take_over(
        lead_id: UUID,
        profile: Annotated[Profile, Depends(can_act)],
        actions: Annotated[LeadActions, Depends(actions_factory)],
        get: Annotated[GetLead, Depends(get_factory)],
        delivery: Annotated[OutboundRepository, Depends(delivery_factory)],
    ) -> LeadDetailRead:
        with _errors():
            actions.take_over.execute(profile.tenant_id, lead_id, actor(profile))
        return refreshed(lead_id, profile, get, delivery)

    @router.post("/leads/{lead_id}/release", response_model=LeadDetailRead)
    def release(
        lead_id: UUID,
        profile: Annotated[Profile, Depends(can_act)],
        actions: Annotated[LeadActions, Depends(actions_factory)],
        get: Annotated[GetLead, Depends(get_factory)],
        delivery: Annotated[OutboundRepository, Depends(delivery_factory)],
    ) -> LeadDetailRead:
        with _errors():
            actions.release.execute(profile.tenant_id, lead_id, actor(profile))
        return refreshed(lead_id, profile, get, delivery)

    @router.post("/leads/{lead_id}/messages", response_model=MessageRead, status_code=201)
    def reply(
        lead_id: UUID,
        payload: TeamMessageWrite,
        profile: Annotated[Profile, Depends(can_act)],
        actions: Annotated[LeadActions, Depends(actions_factory)],
    ) -> MessageRead:
        with _errors():
            message = actions.reply.execute(
                profile.tenant_id, lead_id, actor(profile), payload.text
            )
        return message_read(message, author_name=actor(profile).name)

    @router.post("/leads/{lead_id}/visits/{visit_id}/confirm", response_model=LeadDetailRead)
    def confirm_visit(
        lead_id: UUID,
        visit_id: UUID,
        payload: ConfirmVisitWrite,
        profile: Annotated[Profile, Depends(can_act)],
        actions: Annotated[LeadActions, Depends(actions_factory)],
        get: Annotated[GetLead, Depends(get_factory)],
        delivery: Annotated[OutboundRepository, Depends(delivery_factory)],
    ) -> LeadDetailRead:
        if payload.starts_at is not None and payload.starts_at.tzinfo is None:
            raise ApiError(422, "validation_error")
        with _errors():
            actions.confirm.execute(
                profile.tenant_id, lead_id, visit_id, actor(profile), payload.starts_at
            )
        return refreshed(lead_id, profile, get, delivery)

    @router.post("/leads/{lead_id}/visits/{visit_id}/cancel", response_model=LeadDetailRead)
    def cancel_visit(
        lead_id: UUID,
        visit_id: UUID,
        payload: CancelVisitWrite,
        profile: Annotated[Profile, Depends(can_act)],
        actions: Annotated[LeadActions, Depends(actions_factory)],
        get: Annotated[GetLead, Depends(get_factory)],
        delivery: Annotated[OutboundRepository, Depends(delivery_factory)],
    ) -> LeadDetailRead:
        with _errors():
            actions.cancel.execute(
                profile.tenant_id, lead_id, visit_id, actor(profile), payload.message
            )
        return refreshed(lead_id, profile, get, delivery)

    return router


class _errors:
    """Domain errors of the team's actions as stable API codes."""

    _CODES: dict[type[Exception], tuple[int, str]] = {
        LeadNotFoundError: (404, "lead_not_found"),
        VisitNotFoundError: (404, "visit_not_found"),
        ConversationNotTakenError: (409, "conversation_not_taken"),
        OutsideServiceWindowError: (409, "outside_service_window"),
        TemplateNotConfiguredError: (409, "template_not_configured"),
        VisitCancelledError: (409, "visit_cancelled"),
        InvalidLeadTransitionError: (409, "invalid_lead_status"),
        VisitTimeInPastError: (422, "visit_time_in_past"),
        InvalidMessageError: (422, "validation_error"),
    }

    def __enter__(self) -> None:
        return None

    def __exit__(self, kind, error, _traceback) -> bool:
        if error is None:
            return False
        for error_type, (status, code) in self._CODES.items():
            if isinstance(error, error_type):
                raise ApiError(status, code) from error
        return False
