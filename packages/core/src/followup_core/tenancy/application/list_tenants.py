from collections.abc import Sequence

from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository


class ListTenants:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    def execute(self) -> Sequence[Tenant]:
        return self._repository.list_all()
