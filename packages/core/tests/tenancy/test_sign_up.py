from uuid import UUID, uuid4

import pytest
from followup_core.identity.domain.profile import Profile, Role
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.domain.errors import (
    DuplicateTenantSlugError,
    InvalidTenantNameError,
)
from followup_core.tenancy.domain.tenant import Tenant, TenantStatus


class InMemoryTenantRepository:
    def __init__(self) -> None:
        self.tenants: dict[UUID, Tenant] = {}
        self.slugs: set[str] = set()

    def add(self, tenant: Tenant) -> None:
        self.tenants[tenant.id] = tenant
        self.slugs.add(tenant.slug)

    def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        return self.tenants.get(tenant_id)

    def list_page(self, page: int, limit: int) -> list[Tenant]:
        offset = (page - 1) * limit
        return list(self.tenants.values())[offset : offset + limit]

    def count(self) -> int:
        return len(self.tenants)

    def slug_exists(self, slug: str) -> bool:
        return slug in self.slugs


class InMemoryProfileRepository:
    def __init__(self) -> None:
        self.profiles: dict[UUID, Profile] = {}

    def get_by_id(self, user_id: UUID) -> Profile | None:
        return self.profiles.get(user_id)

    def add(self, profile: Profile) -> None:
        self.profiles[profile.id] = profile


def test_sign_up_creates_tenant_owner_and_trial() -> None:
    tenants = InMemoryTenantRepository()
    profiles = InMemoryProfileRepository()
    user_id = uuid4()

    result = SignUp(tenants, profiles).execute(
        user_id=user_id,
        email="owner@example.com",
        business_name="Inmobiliaria Sur",
    )

    assert result.created is True
    assert result.tenant.status == TenantStatus.ACTIVE
    assert result.tenant.trial_ends_at > result.tenant.created_at
    assert result.profile.tenant_id == result.tenant.id
    assert result.profile.role == Role.OWNER
    assert result.profile.is_platform_admin is False
    assert profiles.get_by_id(user_id) == result.profile
    assert tenants.get_by_id(result.tenant.id) == result.tenant


def test_sign_up_is_idempotent_per_user() -> None:
    tenants = InMemoryTenantRepository()
    profiles = InMemoryProfileRepository()
    user_id = uuid4()

    first = SignUp(tenants, profiles).execute(
        user_id=user_id,
        email="owner@example.com",
        business_name="Inmobiliaria Sur",
    )
    second = SignUp(tenants, profiles).execute(
        user_id=user_id,
        email="owner@example.com",
        business_name="Otro Nombre",
    )

    assert second.created is False
    assert second.tenant.id == first.tenant.id
    assert len(tenants.tenants) == 1
    assert len(profiles.profiles) == 1


def test_sign_up_rejects_blank_business_name() -> None:
    with pytest.raises(InvalidTenantNameError):
        SignUp(InMemoryTenantRepository(), InMemoryProfileRepository()).execute(
            user_id=uuid4(),
            email="owner@example.com",
            business_name="   ",
        )


def test_sign_up_rejects_duplicate_slug_for_different_users() -> None:
    tenants = InMemoryTenantRepository()
    profiles = InMemoryProfileRepository()

    SignUp(tenants, profiles).execute(
        user_id=uuid4(),
        email="a@example.com",
        business_name="Inmobiliaria Sur",
    )

    with pytest.raises(DuplicateTenantSlugError):
        SignUp(tenants, profiles).execute(
            user_id=uuid4(),
            email="b@example.com",
            business_name="Inmobiliaria Sur",
        )
