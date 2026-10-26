from ..domain.errors import DuplicateTenantSlugError
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository


class CreateTenant:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    def execute(self, name: str) -> Tenant:
        tenant = Tenant.create(name)
        if self._repository.slug_exists(tenant.slug):
            raise DuplicateTenantSlugError(f"Tenant slug '{tenant.slug}' already exists.")

        self._repository.add(tenant)
        return tenant
