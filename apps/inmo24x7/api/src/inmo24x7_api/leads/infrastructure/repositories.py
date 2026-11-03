from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..domain.lead import (
    WAITING_FOR_TEAM,
    HandOffReason,
    Lead,
    LeadStatus,
    StatusChange,
    Visit,
    VisitStatus,
)
from ..domain.repositories import InboxTab, LeadFilters, LeadPage, Search
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
            last_human_reply_at=model.last_human_reply_at,
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
        model.last_human_reply_at = lead.last_human_reply_at
        model.search_text = lead.search_text
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

    def _conditions(self, tenant_id: UUID, filters: LeadFilters) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [LeadModel.tenant_id == tenant_id]
        if not filters.include_test:
            conditions.append(~LeadModel.is_test)
        conditions.extend(_search_conditions(filters.search))
        return conditions

    def _count(self, conditions: Sequence[ColumnElement[bool]]) -> int:
        statement = select(func.count()).select_from(LeadModel).where(*conditions)
        return self._session.scalar(statement) or 0

    def _ordered(self, tenant_id: UUID, filters: LeadFilters):
        conditions = [*self._conditions(tenant_id, filters), *_tab_conditions(filters.tab)]
        return select(LeadModel).where(*conditions).order_by(*_tab_order(filters.tab)), conditions

    def list(self, tenant_id: UUID, filters: LeadFilters, page: int, page_size: int) -> LeadPage:
        statement, conditions = self._ordered(tenant_id, filters)
        base = self._conditions(tenant_id, filters)
        counts = {tab: self._count([*base, *_tab_conditions(tab)]) for tab in InboxTab}
        models = self._session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
        items = [self._to_domain(model) for model in models]
        next_visits: dict[UUID, datetime] = {}
        if items:
            rows = self._session.execute(
                select(VisitModel.lead_id, func.min(VisitModel.starts_at))
                .where(
                    VisitModel.lead_id.in_([item.id for item in items]),
                    VisitModel.status.in_(_ACTIVE_VISITS),
                )
                .group_by(VisitModel.lead_id)
            )
            next_visits = {lead_id: starts_at for lead_id, starts_at in rows}
        return LeadPage(
            items=items,
            total=counts[filters.tab],
            page=page,
            page_size=page_size,
            counts=counts,
            next_visits=next_visits,
        )

    def export(self, tenant_id: UUID, filters: LeadFilters, limit: int) -> Sequence[Lead]:
        statement, _ = self._ordered(tenant_id, filters)
        return [self._to_domain(model) for model in self._session.scalars(statement.limit(limit))]

    def latest_visits(self, lead_ids: Sequence[UUID]) -> Mapping[UUID, Visit]:
        if not lead_ids:
            return {}
        rows = self._session.scalars(
            select(VisitModel)
            .where(VisitModel.lead_id.in_(lead_ids))
            .order_by(VisitModel.created_at)
        )
        # Oldest first, so each lead keeps its newest visit.
        return {row.lead_id: _visit(row) for row in rows}

    def visits(self, lead_id: UUID) -> Sequence[Visit]:
        rows = self._session.scalars(
            select(VisitModel).where(VisitModel.lead_id == lead_id).order_by(VisitModel.created_at)
        )
        return [_visit(row) for row in rows]

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

    def save_visit(self, visit: Visit) -> None:
        model = self._session.get(VisitModel, visit.id)
        if model is not None:
            model.status = visit.status.value
            model.starts_at = visit.starts_at
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


_ACTIVE_VISITS = (VisitStatus.PROPOSED.value, VisitStatus.CONFIRMED.value)


def _visit(row: VisitModel) -> Visit:
    return Visit(
        id=row.id,
        lead_id=row.lead_id,
        property_id=row.property_id,
        property_label=row.property_label,
        starts_at=row.starts_at,
        status=VisitStatus(row.status),
        created_at=row.created_at,
    )


def attention_condition() -> ColumnElement[bool]:
    """`Lead.needs_attention` in SQL (tests check that both agree)."""
    return and_(
        LeadModel.status.in_([status.value for status in WAITING_FOR_TEAM]),
        or_(
            LeadModel.last_human_reply_at.is_(None),
            and_(
                LeadModel.handed_off_at.is_not(None),
                LeadModel.last_human_reply_at < LeadModel.handed_off_at,
            ),
        ),
    )


def _visit_time(*statuses: str) -> Any:
    return (
        select(func.min(VisitModel.starts_at))
        .where(VisitModel.lead_id == LeadModel.id, VisitModel.status.in_(statuses))
        .correlate(LeadModel)
        .scalar_subquery()
    )


def _tab_conditions(tab: InboxTab) -> list[ColumnElement[bool]]:
    match tab:
        case InboxTab.ATTENTION:
            return [attention_condition()]
        case InboxTab.VISITS:
            return [_visit_time(*_ACTIVE_VISITS).is_not(None)]
        case InboxTab.ALL:
            return []


def _tab_order(tab: InboxTab) -> list[Any]:
    match tab:
        case InboxTab.ATTENTION:
            # Someone asked for a person first, then the soonest proposed visit, then the
            # oldest hand-off.
            return [
                case((LeadModel.status == LeadStatus.HUMAN_REQUESTED.value, 0), else_=1),
                _visit_time(VisitStatus.PROPOSED.value).asc().nulls_last(),
                LeadModel.handed_off_at.asc().nulls_last(),
                LeadModel.id,
            ]
        case InboxTab.VISITS:
            return [_visit_time(*_ACTIVE_VISITS).asc(), LeadModel.id]
        case InboxTab.ALL:
            return [LeadModel.last_activity_at.desc(), LeadModel.id]


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _search_conditions(search: Search) -> list[ColumnElement[bool]]:
    if search.digits:
        return [LeadModel.search_text.like(_like(search.digits))]
    if search.text:
        return [LeadModel.search_text.like(_like(search.text))]
    return []
