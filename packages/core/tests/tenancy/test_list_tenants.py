from datetime import UTC, datetime, timedelta
from uuid import uuid4

from followup_core.tenancy.application.list_tenants import ListTenants
from followup_core.tenancy.domain.tenant import Tenant, TenantStatus


class InMemoryTenantRepository:
    def __init__(self, tenants: list[Tenant]) -> None:
        self.tenants = tenants

    def add(self, tenant: Tenant) -> None:
        self.tenants.append(tenant)

    def save(self, tenant: Tenant) -> None:
        raise NotImplementedError

    def get_by_id(self, tenant_id) -> Tenant | None:
        return next((tenant for tenant in self.tenants if tenant.id == tenant_id), None)

    def list_page(self, page: int, limit: int) -> list[Tenant]:
        offset = (page - 1) * limit
        return self.tenants[offset : offset + limit]

    def count(self) -> int:
        return len(self.tenants)

    def slug_exists(self, slug: str) -> bool:
        return any(tenant.slug == slug for tenant in self.tenants)


def test_list_tenants_returns_a_page() -> None:
    tenant = Tenant(
        id=uuid4(),
        name="Inmobiliaria Sur",
        slug="inmobiliaria-sur",
        created_at=datetime.now(UTC),
        status=TenantStatus.ACTIVE,
        trial_ends_at=datetime.now(UTC) + timedelta(days=14),
    )

    result = ListTenants(InMemoryTenantRepository([tenant])).execute(page=1, limit=10)

    assert result.items == [tenant]
    assert result.page == 1
    assert result.limit == 10
    assert result.total == 1
    assert result.total_pages == 1
