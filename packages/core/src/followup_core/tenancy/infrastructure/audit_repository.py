from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..domain.audit import ActorKind, AuditAction, AuditEvent
from ..domain.owner_claims import OwnerClaim
from .models import AuditEventModel, OwnerClaimModel


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlAlchemyAuditLog:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, event: AuditEvent) -> None:
        statement = insert(AuditEventModel).values(
            id=event.id,
            tenant_id=event.tenant_id,
            at=event.at,
            actor_kind=event.actor_kind.value,
            actor_profile_id=event.actor_profile_id,
            action=event.action.value,
            details=dict(event.details),
            dedupe_key=event.dedupe_key,
        )
        if event.dedupe_key is not None:
            statement = statement.on_conflict_do_nothing(index_elements=["dedupe_key"])
        self._session.execute(statement)

    def latest(self, tenant_id: UUID, limit: int) -> Sequence[AuditEvent]:
        models = self._session.scalars(
            select(AuditEventModel)
            .where(AuditEventModel.tenant_id == tenant_id)
            .order_by(AuditEventModel.at.desc(), AuditEventModel.id)
            .limit(limit)
        ).all()
        return [
            AuditEvent(
                id=model.id,
                tenant_id=model.tenant_id,
                at=_aware(model.at),
                actor_kind=ActorKind(model.actor_kind),
                action=AuditAction(model.action),
                details=model.details,
                actor_profile_id=model.actor_profile_id,
                dedupe_key=model.dedupe_key,
            )
            for model in models
        ]


class SqlAlchemyOwnerClaimRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_open(self, email: str) -> OwnerClaim | None:
        model = self._session.get(OwnerClaimModel, email.strip().lower())
        if model is None or model.claimed_at is not None:
            return None
        return OwnerClaim(model.email, model.tenant_id, _aware(model.created_at))

    def exists(self, email: str) -> bool:
        return self._session.get(OwnerClaimModel, email.strip().lower()) is not None

    def add(self, claim: OwnerClaim) -> None:
        self._session.add(
            OwnerClaimModel(
                email=claim.email.strip().lower(),
                tenant_id=claim.tenant_id,
                created_at=claim.created_at,
            )
        )
        self._session.flush()

    def mark_claimed(self, email: str, at: datetime) -> None:
        model = self._session.get(OwnerClaimModel, email.strip().lower())
        if model is not None:
            model.claimed_at = at
            self._session.flush()
