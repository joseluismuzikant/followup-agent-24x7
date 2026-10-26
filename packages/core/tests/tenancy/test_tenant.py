from datetime import UTC, datetime
from uuid import uuid4

import pytest
from followup_core.tenancy.domain.errors import (
    InvalidTenantNameError,
    InvalidTenantSlugError,
)
from followup_core.tenancy.domain.tenant import Tenant


def build_tenant(name: str = "Inmobiliaria Sur", slug: str = "inmobiliaria-sur") -> Tenant:
    return Tenant(
        id=uuid4(),
        name=name,
        slug=slug,
        created_at=datetime.now(UTC),
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
