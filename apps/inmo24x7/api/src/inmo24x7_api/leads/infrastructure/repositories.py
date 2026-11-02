from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..domain.lead import (
    HandOffReason,
    Lead,
    LeadStatus,
    StatusChange,
    Visit,
    VisitStatus,
)
from ..domain.repositories import LeadFilters, LeadPage
from .models import LeadModel, LeadPropertyMatchModel, LeadStatusChangeModel, VisitModel


class SqlAlchemyLeadRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _history(self, lead_id: UUID) -> tuple[StatusChange, ...]:
        rows = self._session.scalars(
            select(LeadStatusChangeModel)
            .where(LeadStatusChangeModel.lead_id == lead_id)
            .order_by(LeadStatusChangeModel.position)
        )
        return tuple(StatusChange(LeadStatus(row.status), row.changed_at) for row in rows)

    def _to_domain(self, model: LeadModel) -> Lead:
        return Lead(
            id=model.id,
            tenant_id=model.tenant_id,
            thread_id=model.thread_id,
            thread_key=model.thread_key,
            channel=model.channel,
            is_test=model.is_test,
            visitor_name=model.visitor_name,
            contact=model.contact,
            answers=dict(model.answers),
            status=LeadStatus(model.status),
            history=self._history(model.id),
            handed_off_at=model.handed_off_at,
            hand_off_reason=HandOffReason(model.hand_off_reason) if model.hand_off_reason else None,
            created_at=model.created_at,
            last_activity_at=model.last_activity_at,
        )

    def get(self, tenant_id: UUID, lead_id: UUID) -> Lead | None:
        model = self._session.get(LeadModel, lead_id)
        if model is None or model.tenant_id != tenant_id:
            return None
        return self._to_domain(model)

    def get_by_thread(self, thread_id: UUID) -> Lead | None:
        model = self._session.scalar(select(LeadModel).where(LeadModel.thread_id == thread_id))
        return self._to_domain(model) if model is not None else None

    def save(self, lead: Lead) -> None:
        model = self._session.get(LeadModel, lead.id)
        stored = 0
        if model is None:
            model = LeadModel(
                id=lead.id,
                tenant_id=lead.tenant_id,
                thread_id=lead.thread_id,
                thread_key=lead.thread_key,
                channel=lead.channel,
                is_test=lead.is_test,
                created_at=lead.created_at,
            )
            self._session.add(model)
        else:
            stored = len(self._history(lead.id))
        model.visitor_name = lead.visitor_name
        model.contact = lead.contact
        model.answers = dict(lead.answers)
        model.status = lead.status.value
        model.handed_off_at = lead.handed_off_at
        model.hand_off_reason = lead.hand_off_reason.value if lead.hand_off_reason else None
        model.last_activity_at = lead.last_activity_at
        self._session.flush()
        for position, change in enumerate(lead.history[stored:], start=stored):
            self._session.add(
                LeadStatusChangeModel(
                    id=uuid4(),
                    lead_id=lead.id,
                    position=position,
                    status=change.status.value,
                    changed_at=change.changed_at,
                )
            )
        self._session.flush()

    def list(self, tenant_id: UUID, filters: LeadFilters, page: int, page_size: int) -> LeadPage:
        conditions = [LeadModel.tenant_id == tenant_id]
        if filters.status is not None:
            conditions.append(LeadModel.status == filters.status.value)
        if not filters.include_test:
            conditions.append(~LeadModel.is_test)
        total = (
            self._session.scalar(select(func.count()).select_from(LeadModel).where(*conditions))
            or 0
        )
        models = self._session.scalars(
            select(LeadModel)
            .where(*conditions)
            .order_by(LeadModel.last_activity_at.desc(), LeadModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return LeadPage(
            items=[self._to_domain(model) for model in models],
            total=total,
            page=page,
            page_size=page_size,
        )

    def visits(self, lead_id: UUID) -> Sequence[Visit]:
        rows = self._session.scalars(
            select(VisitModel).where(VisitModel.lead_id == lead_id).order_by(VisitModel.created_at)
        )
        return [
            Visit(
                id=row.id,
                lead_id=row.lead_id,
                property_id=row.property_id,
                property_label=row.property_label,
                starts_at=row.starts_at,
                status=VisitStatus(row.status),
                created_at=row.created_at,
            )
            for row in rows
        ]

    def add_visit(self, visit: Visit) -> None:
        self._session.add(
            VisitModel(
                id=visit.id,
                lead_id=visit.lead_id,
                property_id=visit.property_id,
                property_label=visit.property_label,
                starts_at=visit.starts_at,
                status=visit.status.value,
                created_at=visit.created_at,
            )
        )
        self._session.flush()

    def record_matches(
        self, lead_id: UUID, property_ids: Iterable[UUID], shown_at: datetime
    ) -> None:
        ids = list(dict.fromkeys(property_ids))
        if not ids:
            return
        self._session.execute(
            insert(LeadPropertyMatchModel)
            .values(
                [{"lead_id": lead_id, "property_id": item, "shown_at": shown_at} for item in ids]
            )
            .on_conflict_do_nothing(index_elements=["lead_id", "property_id"])
        )
