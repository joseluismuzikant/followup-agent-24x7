import pytest
from followup_core.tenancy.application.create_tenant import CreateTenant
from followup_core.tenancy.domain.errors import (
    DuplicateTenantSlugError,
    InvalidTenantNameError,
)
from followup_core.tenancy.domain.tenant import Tenant


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.tenants: list[Tenant] = []

    def add(self, tenant: Tenant) -> None:
        self.tenants.append(tenant)

    def get_by_id(self, tenant_id) -> Tenant | None:
        return next((tenant for tenant in self.tenants if tenant.id == tenant_id), None)

    def list_page(self, page: int, limit: int) -> list[Tenant]:
        offset = (page - 1) * limit
        return self.tenants[offset : offset + limit]

    def count(self) -> int:
        return len(self.tenants)

    def slug_exists(self, slug: str) -> bool:
        return any(tenant.slug == slug for tenant in self.tenants)


def test_create_tenant_uses_a_normalized_slug() -> None:
    repository = InMemoryTenantRepository()

    tenant = CreateTenant(repository).execute("  Inmobiliaria Ñandú  ")

    assert tenant.name == "Inmobiliaria Ñandú"
    assert tenant.slug == "inmobiliaria-nandu"
    assert repository.tenants == [tenant]


def test_create_tenant_rejects_duplicate_slug() -> None:
    repository = InMemoryTenantRepository()
    use_case = CreateTenant(repository)
    use_case.execute("Inmobiliaria Sur")

    with pytest.raises(DuplicateTenantSlugError):
        use_case.execute("  inmobiliaria sur ")


def test_create_tenant_rejects_blank_name() -> None:
    with pytest.raises(InvalidTenantNameError):
        CreateTenant(InMemoryTenantRepository()).execute("   ")
