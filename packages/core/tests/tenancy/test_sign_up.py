from uuid import uuid4

import pytest
from followup_core.identity.domain.profile import Role
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.domain.business_settings import BusinessType
from followup_core.tenancy.domain.errors import InvalidBusinessTypeError, InvalidTenantNameError
from followup_core.tenancy.domain.onboarding import OnboardingStep
from followup_core.tenancy.domain.tenant import TenantStatus
from tenancy_fakes import (
    InMemoryBusinessSettingsRepository,
    InMemoryOnboardingRepository,
    InMemoryProfileRepository,
    InMemoryTenantRepository,
    sample_defaults,
)


def _sign_up_use_case(tenants=None, profiles=None, onboardings=None, settings=None) -> SignUp:
    return SignUp(
        tenants or InMemoryTenantRepository(),
        profiles or InMemoryProfileRepository(),
        onboardings or InMemoryOnboardingRepository(),
        settings or InMemoryBusinessSettingsRepository(),
        sample_defaults(),
    )


def test_sign_up_creates_tenant_owner_and_trial() -> None:
    tenants = InMemoryTenantRepository()
    profiles = InMemoryProfileRepository()
    user_id = uuid4()

    result = _sign_up_use_case(tenants, profiles).execute(
        user_id=user_id,
        email="owner@example.com",
        business_name="Inmobiliaria Sur",
        business_type="inmobiliaria",
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

    first = _sign_up_use_case(tenants, profiles).execute(
        user_id=user_id,
        email="owner@example.com",
        business_name="Inmobiliaria Sur",
        business_type="inmobiliaria",
    )
    second = _sign_up_use_case(tenants, profiles).execute(
        user_id=user_id,
        email="owner@example.com",
        business_name="Otro Nombre",
        business_type="inmobiliaria",
    )

    assert second.created is False
    assert second.tenant.id == first.tenant.id
    assert len(tenants.tenants) == 1
    assert len(profiles.profiles) == 1


def test_sign_up_rejects_blank_business_name() -> None:
    with pytest.raises(InvalidTenantNameError):
        _sign_up_use_case().execute(
            user_id=uuid4(),
            email="owner@example.com",
            business_name="   ",
            business_type="inmobiliaria",
        )


def test_sign_up_picks_next_free_slug_for_same_business_name() -> None:
    tenants = InMemoryTenantRepository()
    profiles = InMemoryProfileRepository()

    slugs = [
        _sign_up_use_case(tenants, profiles)
        .execute(
            user_id=uuid4(),
            email=f"user{index}@example.com",
            business_name="Inmobiliaria Sur",
            business_type="inmobiliaria",
        )
        .tenant.slug
        for index in range(3)
    ]

    assert slugs == ["inmobiliaria-sur", "inmobiliaria-sur-2", "inmobiliaria-sur-3"]


def test_sign_up_creates_onboarding_and_default_settings() -> None:
    onboardings = InMemoryOnboardingRepository()
    settings = InMemoryBusinessSettingsRepository()

    result = _sign_up_use_case(onboardings=onboardings, settings=settings).execute(
        user_id=uuid4(),
        email="Owner@Example.com",
        business_name="Inmobiliaria Sur",
        business_type="corredor",
    )

    onboarding = onboardings.get(result.tenant.id)
    assert onboarding is not None
    assert onboarding.current_step is OnboardingStep.AGENT
    assert OnboardingStep.BUSINESS in onboarding.completed_steps
    saved = settings.get(result.tenant.id)
    assert saved is not None
    assert saved.business_type is BusinessType.BROKER
    assert saved.notification_emails == ("owner@example.com",)
    assert saved.team_hours == sample_defaults().team_hours


def test_sign_up_rejects_unknown_business_type() -> None:
    tenants = InMemoryTenantRepository()

    with pytest.raises(InvalidBusinessTypeError):
        _sign_up_use_case(tenants).execute(
            user_id=uuid4(),
            email="owner@example.com",
            business_name="Inmobiliaria Sur",
            business_type="pizzeria",
        )

    assert tenants.count() == 0
