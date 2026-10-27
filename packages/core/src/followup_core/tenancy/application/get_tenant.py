from uuid import UUID

from ..domain.errors import TenantNotFoundError
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository


class GetTenant:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    def execute(self, tenant_id: UUID) -> Tenant:
        tenant = self._repository.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' does not exist.")
        return tenant
