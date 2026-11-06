from collections.abc import Sequence
from datetime import UTC
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.errors import DuplicateTenantSlugError, TenantNotFoundError
from ..domain.product import FIRST_PRODUCT, Product
from ..domain.tenant import Plan, Tenant, TenantStatus
from .models import TenantModel


def _to_domain(model: TenantModel) -> Tenant:
    created_at = model.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    trial_ends_at = model.trial_ends_at
    if trial_ends_at.tzinfo is None:
        trial_ends_at = trial_ends_at.replace(tzinfo=UTC)
    suspended_at = model.suspended_at
    if suspended_at is not None and suspended_at.tzinfo is None:
        suspended_at = suspended_at.replace(tzinfo=UTC)

    return Tenant(
        id=model.id,
        name=model.name,
        slug=model.slug,
        created_at=created_at,
        status=TenantStatus(model.status),
        trial_ends_at=trial_ends_at,
        plan=Plan(model.plan),
        suspended_reason=model.suspended_reason,
        suspended_at=suspended_at,
        product=Product(model.product),
    )


class SqlAlchemyTenantRepository:
    """One product's tenants: a tenant of another product does not exist here."""

    def __init__(self, session: Session, product: Product = FIRST_PRODUCT) -> None:
        self._session = session
        self._product = product

    def _get(self, tenant_id: UUID) -> TenantModel | None:
        model = self._session.get(TenantModel, tenant_id)
        return model if model is not None and model.product == self._product else None

    def add(self, tenant: Tenant) -> None:
        if tenant.product != self._product:
            raise ValueError(f"A {tenant.product} tenant in the {self._product} repository.")
        self._session.add(
            TenantModel(
                id=tenant.id,
                product=tenant.product.value,
                name=tenant.name,
                slug=tenant.slug,
                created_at=tenant.created_at,
                status=tenant.status.value,
                trial_ends_at=tenant.trial_ends_at,
                plan=tenant.plan.value,
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
        model = self._get(tenant.id)
        if model is None:
            raise TenantNotFoundError(f"Tenant '{tenant.id}' does not exist.")
        model.name = tenant.name
        model.status = tenant.status.value
        model.plan = tenant.plan.value
        model.suspended_reason = tenant.suspended_reason
        model.suspended_at = tenant.suspended_at
        self._session.flush()

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        model = self._get(tenant_id)
        return _to_domain(model) if model is not None else None

    def list_page(self, page: int, limit: int) -> Sequence[Tenant]:
        offset = (page - 1) * limit
        models = self._session.scalars(
            select(TenantModel)
            .where(TenantModel.product == self._product)
            .order_by(TenantModel.created_at.desc(), TenantModel.id)
            .offset(offset)
            .limit(limit)
        ).all()
        return [_to_domain(model) for model in models]

    def count(self) -> int:
        return (
            self._session.scalar(
                select(func.count())
                .select_from(TenantModel)
                .where(TenantModel.product == self._product)
            )
            or 0
        )

    def slug_exists(self, slug: str) -> bool:
        return bool(
            self._session.scalar(
                select(
                    exists().where(TenantModel.slug == slug, TenantModel.product == self._product)
                )
            )
        )
