from collections.abc import Sequence
from datetime import UTC
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.errors import DuplicateTenantSlugError, TenantNotFoundError
from ..domain.tenant import Tenant, TenantStatus
from .models import TenantModel


def _to_domain(model: TenantModel) -> Tenant:
    created_at = model.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    trial_ends_at = model.trial_ends_at
    if trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=UTC)

    return Tenant(
        id=model.id,
        name=model.name,
        slug=model.slug,
        created_at=created_at,
        status=TenantStatus(model.status),
        trial_ends_at=trial_ends_at,
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
                status=tenant.status.value,
                trial_ends_at=tenant.trial_ends_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            self._session.rollback()
            raise DuplicateTenantSlugError(
                f"Tenant slug '{tenant.slug}' already exists."
            ) from error

    def save(self, tenant: Tenant) -> None:
        model = self._session.get(TenantModel, tenant.id)
        if model is None:
            raise TenantNotFoundError(f"Tenant '{tenant.id}' does not exist.")
        model.name = tenant.name
        model.status = tenant.status.value
        self._session.flush()

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        model = self._session.get(TenantModel, tenant_id)
        return _to_domain(model) if model is not None else None

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
