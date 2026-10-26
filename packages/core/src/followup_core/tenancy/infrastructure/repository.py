from collections.abc import Sequence
from datetime import UTC

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.errors import DuplicateTenantSlugError
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
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise DuplicateTenantSlugError(
                f"Tenant slug '{tenant.slug}' already exists."
            ) from error

    def list_page(self, page: int, limit: int) -> Sequence[Tenant]:
        offset = (page - 1) * limit
        models = self._session.scalars(
            select(TenantModel)
            .order_by(TenantModel.created_at.desc(), TenantModel.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return [_to_domain(model) for model in models]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(TenantModel)) or 0

    def slug_exists(self, slug: str) -> bool:
        return bool(self._session.scalar(select(exists().where(TenantModel.slug == slug))))
