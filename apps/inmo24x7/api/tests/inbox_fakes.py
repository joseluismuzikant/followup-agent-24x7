"""Leads written straight through the repositories (thread, lead, visits, messages), for the
inbox list, export and dashboard tests that need many leads at fixed times."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from followup_core.conversation.domain.thread import (
    Author,
    Channel,
    Direction,
    Message,
    Thread,
    ThreadKey,
    ThreadStatus,
)
from followup_core.conversation.infrastructure.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemyThreadRepository,
)
from inmo24x7_api.leads.domain.lead import (
    HandOffReason,
    Lead,
    LeadStatus,
    StatusChange,
    Visit,
    VisitStatus,
)
from inmo24x7_api.leads.infrastructure.repositories import SqlAlchemyLeadRepository
from sqlalchemy.orm import Session


def add_lead(
    session: Session,
    tenant_id: UUID,
    *,
    created_at: datetime,
    name: str | None = None,
    contact: str | None = None,
    answers: Mapping[str, Any] | None = None,
    status: LeadStatus = LeadStatus.QUALIFYING,
    handed_off_at: datetime | None = None,
    last_human_reply_at: datetime | None = None,
    last_activity_at: datetime | None = None,
    is_test: bool = False,
    visits: Sequence[tuple[datetime, VisitStatus]] = (),
    messages: Sequence[tuple[Author, datetime]] = (),
) -> Lead:
    channel = Channel.SIMULATOR if is_test else Channel.WHATSAPP
    thread = Thread(
        id=uuid4(),
        key=ThreadKey(tenant_id, channel, uuid4().hex),
        agent_config_version=0,
        status=ThreadStatus.OPEN,
        created_at=created_at,
        last_message_at=messages[-1][1] if messages else created_at,
    )
    SqlAlchemyThreadRepository(session).add(thread)
    history = [author_and_time for author_and_time in messages]
    message_repository = SqlAlchemyMessageRepository(session)
    for author, at in history:
        direction = Direction.INBOUND if author is Author.VISITOR else Direction.OUTBOUND
        message_repository.append(Message(uuid4(), thread.id, direction, author, "·", at))
    lead = Lead.start(
        tenant_id=tenant_id,
        thread_id=thread.id,
        thread_key=str(thread.key),
        channel=channel.value,
        is_test=is_test,
        now=created_at,
    )
    lead = replace(
        lead,
        visitor_name=name,
        contact=contact,
        answers=dict(answers or {}),
        status=status,
        history=(*lead.history, StatusChange(status, created_at))
        if status is not LeadStatus.QUALIFYING
        else lead.history,
        handed_off_at=handed_off_at,
        hand_off_reason=HandOffReason.VISIT if handed_off_at else None,
        last_human_reply_at=last_human_reply_at,
        last_activity_at=last_activity_at or created_at,
    )
    leads = SqlAlchemyLeadRepository(session)
    leads.save(lead)
    for starts_at, visit_status in visits:
        leads.add_visit(
            Visit(
                uuid4(), lead.id, None, "Depto · Gorriti 4800", starts_at, visit_status, created_at
            )
        )
    session.commit()
    return lead
