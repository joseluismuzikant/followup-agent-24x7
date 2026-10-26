from datetime import UTC, datetime
from uuid import uuid4

from ..domain.errors import DuplicateTenantSlugError, InvalidTenantNameError
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository
from .slug import slugify


class CreateTenant:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    def execute(self, name: str) -> Tenant:
        normalized_name = name.strip()
        if not normalized_name:
            raise InvalidTenantNameError("Tenant name cannot be empty.")

        slug = slugify(normalized_name)
        if self._repository.slug_exists(slug):
            raise DuplicateTenantSlugError(f"Tenant slug '{slug}' already exists.")

        tenant = Tenant(
            id=uuid4(),
            name=normalized_name,
            slug=slug,
            created_at=datetime.now(UTC),
        )
        self._repository.add(tenant)
        return tenant
