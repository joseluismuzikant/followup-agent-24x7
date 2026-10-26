from collections.abc import Sequence
from datetime import UTC

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..domain.tenant import Tenant
from .models import TenantModel


def _to_domain(model: TenantModel) -> Tenant:
    created_at = model.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    return Tenant(
        id=model.id,
        name=model.name,
        slug=model.slug,
        created_at=created_at,
    )


class SqlAlchemyTenantRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, tenant: Tenant) -> None:
        self._session.add(
            TenantModel(
                id=tenant.id,
                name=tenant.name,
                slug=tenant.slug,
                created_at=tenant.created_at,
            )
        )
        self._session.flush()

    def list_all(self) -> Sequence[Tenant]:
        models = self._session.scalars(
            select(TenantModel).order_by(TenantModel.created_at.desc())
        ).all()
        return [_to_domain(model) for model in models]

    def slug_exists(self, slug: str) -> bool:
        return bool(self._session.scalar(select(exists().where(TenantModel.slug == slug))))
