from collections.abc import Sequence
from dataclasses import dataclass

from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository


@dataclass(frozen=True, slots=True)
class TenantPage:
    items: Sequence[Tenant]
    page: int
    limit: int
    total: int

    @property
    def total_pages(self) -> int:
        if self.total == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit


class ListTenants:
    def __init__(self, repository: TenantRepository) -> None:
        self._repository = repository

    def execute(self, page: int, limit: int) -> TenantPage:
        return TenantPage(
            items=self._repository.list_page(page, limit),
            page=page,
            limit=limit,
            total=self._repository.count(),
        )
