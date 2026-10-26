from datetime import UTC, datetime
from uuid import uuid4

from followup_core.tenancy.application.list_tenants import ListTenants
from followup_core.tenancy.domain.tenant import Tenant


class InMemoryTenantRepository:
    def __init__(self, tenants: list[Tenant]) -> None:
        self.tenants = tenants

    def add(self, tenant: Tenant) -> None:
        self.tenants.append(tenant)

    def list_all(self) -> list[Tenant]:
        return list(self.tenants)

    def slug_exists(self, slug: str) -> bool:
        return any(tenant.slug == slug for tenant in self.tenants)


def test_list_tenants_returns_repository_items() -> None:
    tenant = Tenant(
        id=uuid4(),
        name="Inmobiliaria Sur",
        slug="inmobiliaria-sur",
        created_at=datetime.now(UTC),
    )

    result = ListTenants(InMemoryTenantRepository([tenant])).execute()

    assert result == [tenant]
