from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from followup_core.messaging.infrastructure.models import DoNotContactModel
from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ...properties.infrastructure.models import PropertyModel
from ..domain.lead import (
    WAITING_FOR_TEAM,
    HandOffReason,
    Lead,
    LeadStatus,
    StatusChange,
    Visit,
    VisitStatus,
)
from ..domain.repositories import (
    ConditionCounts,
    Evaluation,
    InboxTab,
    LeadFilters,
    LeadPage,
    Search,
    StoredMatch,
    lead_status,
)
from .models import (
    LeadConditionEventModel,
    LeadModel,
    LeadPropertyMatchModel,
    LeadStatusChangeModel,
    VisitModel,
)


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

    def _opted_out(self, model: LeadModel) -> bool:
        if model.channel != "whatsapp":
            return False
        wa_id = model.thread_key.rsplit(":", 1)[-1]
        return self._session.get(DoNotContactModel, (model.tenant_id, wa_id)) is not None

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
            conditions_status=model.conditions_status,
            do_not_contact=self._opted_out(model),
            source=model.source,
        )

    def get(self, tenant_id: UUID, lead_id: UUID) -> Lead | None:
        model = self._session.get(LeadModel, lead_id)
        if model is None or model.tenant_id != tenant_id:
            return None
        return self._to_domain(model)

    def get_by_thread(self, thread_id: UUID) -> Lead | None:
        model = self._session.scalar(select(LeadModel).where(LeadModel.thread_id == thread_id))
        return self._to_domain(model) if model is not None else None

    def get_by_thread_key(self, thread_key: str) -> Lead | None:
        model = self._session.scalar(select(LeadModel).where(LeadModel.thread_key == thread_key))
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
        model.source = lead.source
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
        if filters.conditions:
            conditions.append(LeadModel.conditions_status == filters.conditions)
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

    def record_evaluations(
        self, lead_id: UUID, evaluations: Sequence[Evaluation], at: datetime
    ) -> None:
        for item in evaluations:
            match = dict(item.match) if item.match is not None else None
            status = str(match["status"]) if match else None
            statement = insert(LeadPropertyMatchModel).values(
                lead_id=lead_id,
                property_id=item.property_id,
                shown_at=at,
                status=status,
                match=match,
                evaluated_at=at if match else None,
                chosen=item.chosen,
            )
            self._session.execute(
                statement.on_conflict_do_update(
                    index_elements=["lead_id", "property_id"],
                    set_={
                        "status": func.coalesce(
                            statement.excluded.status, LeadPropertyMatchModel.status
                        ),
                        "match": func.coalesce(
                            statement.excluded.match, LeadPropertyMatchModel.match
                        ),
                        "evaluated_at": func.coalesce(
                            statement.excluded.evaluated_at, LeadPropertyMatchModel.evaluated_at
                        ),
                        # Once chosen, always chosen.
                        "chosen": LeadPropertyMatchModel.chosen | statement.excluded.chosen,
                    },
                )
            )

    def matches(self, lead_id: UUID) -> Sequence[StoredMatch]:
        rows = self._session.execute(
            select(LeadPropertyMatchModel, PropertyModel.title, PropertyModel.address)
            .join(PropertyModel, PropertyModel.id == LeadPropertyMatchModel.property_id)
            .where(LeadPropertyMatchModel.lead_id == lead_id)
            .order_by(LeadPropertyMatchModel.chosen.desc(), LeadPropertyMatchModel.shown_at)
        ).all()
        return [
            StoredMatch(
                property_id=row[0].property_id,
                title=row.title,
                address=row.address,
                match=row[0].match,
                chosen=row[0].chosen,
                override_status=row[0].override_status,
                evaluated_at=row[0].evaluated_at,
            )
            for row in rows
        ]

    def refresh_conditions_status(self, lead_id: UUID) -> str | None:
        status = lead_status(self.matches(lead_id))
        model = self._session.get(LeadModel, lead_id)
        if model is not None:
            model.conditions_status = status
            self._session.flush()
        return status

    def override_match(
        self, lead_id: UUID, property_id: UUID, status: str | None, profile_id: UUID, at: datetime
    ) -> bool:
        model = self._session.get(LeadPropertyMatchModel, (lead_id, property_id))
        if model is None:
            return False
        model.override_status = status
        model.overridden_by_profile_id = profile_id if status else None
        model.overridden_at = at if status else None
        self._session.flush()
        return True

    def record_condition_events(
        self,
        tenant_id: UUID,
        lead_id: UUID,
        events: Sequence[tuple[str, UUID | None]],
        at: datetime,
    ) -> None:
        for kind, property_id in events:
            self._session.execute(
                insert(LeadConditionEventModel)
                .values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    kind=kind,
                    dedupe=f"{kind}:{property_id or ''}",
                    property_id=property_id,
                    created_at=at,
                )
                .on_conflict_do_nothing(index_elements=["lead_id", "dedupe"])
            )

    def condition_counts(self, tenant_id: UUID, start: datetime, end: datetime) -> ConditionCounts:
        def count(kind: str) -> int:
            return int(
                self._session.scalar(
                    select(func.count(func.distinct(LeadConditionEventModel.lead_id)))
                    .join(LeadModel, LeadModel.id == LeadConditionEventModel.lead_id)
                    .where(
                        LeadConditionEventModel.tenant_id == tenant_id,
                        LeadConditionEventModel.kind == kind,
                        LeadConditionEventModel.created_at >= start,
                        LeadConditionEventModel.created_at < end,
                        ~LeadModel.is_test,
                    )
                )
                or 0
            )

        return ConditionCounts(count("mismatch"), count("visit_avoided"))


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
