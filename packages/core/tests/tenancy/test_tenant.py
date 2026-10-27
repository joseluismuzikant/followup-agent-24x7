from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from followup_core.tenancy.domain.errors import (
    InvalidTenantNameError,
    InvalidTenantSlugError,
)
from followup_core.tenancy.domain.tenant import Tenant, TenantStatus


def build_tenant(name: str = "Inmobiliaria Sur", slug: str = "inmobiliaria-sur") -> Tenant:
    now = datetime.now(UTC)
    return Tenant(
        id=uuid4(),
        name=name,
        slug=slug,
        created_at=now,
        status=TenantStatus.ACTIVE,
        trial_ends_at=now + timedelta(days=14),
    )


def test_tenant_trims_its_name() -> None:
    tenant = build_tenant(name="  Inmobiliaria Sur  ")

    assert tenant.name == "Inmobiliaria Sur"


def test_tenant_rejects_blank_name() -> None:
    with pytest.raises(InvalidTenantNameError):
        build_tenant(name="   ")


def test_tenant_rejects_invalid_slug() -> None:
    with pytest.raises(InvalidTenantSlugError):
        build_tenant(slug="Inmobiliaria Sur")


def test_tenant_create_normalizes_name_and_derives_slug() -> None:
    tenant = Tenant.create("  Inmobiliaria Ñandú  ")

    assert tenant.name == "Inmobiliaria Ñandú"
    assert tenant.slug == "inmobiliaria-nandu"
    assert tenant.status == TenantStatus.ACTIVE
    assert tenant.trial_ends_at > tenant.created_at
