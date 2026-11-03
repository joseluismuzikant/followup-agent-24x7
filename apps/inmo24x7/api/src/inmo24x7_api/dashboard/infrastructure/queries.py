from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from followup_core.conversation.domain.thread import Author
from followup_core.conversation.infrastructure.models import MessageModel, ThreadModel
from followup_core.messaging.infrastructure.models import WhatsAppOutboundModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...leads.domain.lead import Lead, LeadStatus, VisitStatus
from ...leads.infrastructure.models import LeadModel, VisitModel
from ...leads.infrastructure.repositories import SqlAlchemyLeadRepository
from ..application.get_dashboard import WeekLead
from ..domain.kpis import TranscriptRow


class SqlAlchemyDashboardQueries:
    def __init__(self, session: Session) -> None:
        self._session = session

    def leads_created_since(self, tenant_id: UUID, since: datetime) -> Sequence[WeekLead]:
        rows = self._session.execute(
            select(LeadModel.created_at, LeadModel.answers).where(
                LeadModel.tenant_id == tenant_id,
                ~LeadModel.is_test,
                LeadModel.created_at >= since,
            )
        )
        return [WeekLead(row.created_at, dict(row.answers)) for row in rows]

    def visits_since(self, tenant_id: UUID, since: datetime) -> tuple[int, int]:
        confirmed = VisitModel.status == VisitStatus.CONFIRMED.value
        row = self._session.execute(
            select(func.count(), func.count().filter(confirmed))
            .select_from(VisitModel)
            .join(LeadModel, LeadModel.id == VisitModel.lead_id)
            .where(
                LeadModel.tenant_id == tenant_id,
                ~LeadModel.is_test,
                VisitModel.created_at >= since,
                VisitModel.status.in_([VisitStatus.PROPOSED.value, VisitStatus.CONFIRMED.value]),
            )
        ).one()
        return row[0], row[1]

    def transcript_since(self, tenant_id: UUID, since: datetime) -> Sequence[TranscriptRow]:
        sent = (
            select(func.min(WhatsAppOutboundModel.sent_at))
            .where(WhatsAppOutboundModel.message_id == MessageModel.id)
            .correlate(MessageModel)
            .scalar_subquery()
        )
        rows = self._session.execute(
            select(MessageModel.thread_id, MessageModel.author, MessageModel.created_at, sent)
            .join(LeadModel, LeadModel.thread_id == MessageModel.thread_id)
            .join(ThreadModel, ThreadModel.id == MessageModel.thread_id)
            .where(
                LeadModel.tenant_id == tenant_id,
                ~LeadModel.is_test,
                ThreadModel.last_message_at >= since,
            )
            .order_by(MessageModel.thread_id, MessageModel.seq)
        )
        return [
            TranscriptRow(thread_id, Author(author), created_at, sent_at)
            for thread_id, author, created_at, sent_at in rows
        ]

    def recent_qualifying(self, tenant_id: UUID, limit: int) -> Sequence[Lead]:
        repository = SqlAlchemyLeadRepository(self._session)
        ids = self._session.scalars(
            select(LeadModel.id)
            .where(
                LeadModel.tenant_id == tenant_id,
                ~LeadModel.is_test,
                LeadModel.status == LeadStatus.QUALIFYING.value,
            )
            .order_by(LeadModel.last_activity_at.desc())
            .limit(limit)
        ).all()
        return [lead for lead_id in ids if (lead := repository.get(tenant_id, lead_id))]
