"""Sign-up is invitation-only: it joins the business an admin created for the email."""

from uuid import uuid4

import pytest
from followup_core.identity.domain.profile import Role
from followup_core.tenancy.application.admin_tenants import CreateBusinessForOwner
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.domain.errors import NotInvitedError
from tenancy_fakes import (
    SAMPLE_PRODUCT,
    InMemoryBusinessSettingsRepository,
    InMemoryOnboardingRepository,
    InMemoryOwnerClaims,
    InMemoryProfileRepository,
    InMemoryTenantRepository,
    OnboardingStep,
    RecordingAuditLog,
    sample_defaults,
)


class World:
    def __init__(self) -> None:
        self.tenants = InMemoryTenantRepository()
        self.profiles = InMemoryProfileRepository()
        self.onboardings = InMemoryOnboardingRepository()
        self.claims = InMemoryOwnerClaims()
        self.audit = RecordingAuditLog()
        self.create = CreateBusinessForOwner(
            self.tenants,
            self.profiles,
            self.onboardings,
            InMemoryBusinessSettingsRepository(),
            self.claims,
            sample_defaults(),
            self.audit,
            definition=SAMPLE_PRODUCT,
        )
        self.sign_up = SignUp(
            self.profiles, self.tenants, self.claims, self.audit, definition=SAMPLE_PRODUCT
        )


def test_an_invited_email_joins_its_business_as_owner() -> None:
    world = World()
    tenant = world.create.execute(uuid4(), "Inmobiliaria Sur", "inmobiliaria", "owner@example.com")
    user_id = uuid4()

    result = world.sign_up.execute(user_id, "Owner@Example.com")

    assert result.created is True
    assert result.tenant.id == tenant.id
    assert result.profile.role == Role.OWNER
    assert result.profile.is_platform_admin is False
    assert world.profiles.get_for_user(user_id) == result.profile


def test_sign_up_is_idempotent_per_user() -> None:
    world = World()
    world.create.execute(uuid4(), "Inmobiliaria Sur", "inmobiliaria", "owner@example.com")
    user_id = uuid4()

    first = world.sign_up.execute(user_id, "owner@example.com")
    second = world.sign_up.execute(user_id, "owner@example.com")

    assert second.created is False
    assert second.tenant.id == first.tenant.id
    assert len(world.profiles.profiles) == 1


def test_an_email_nobody_invited_cannot_sign_up() -> None:
    world = World()

    with pytest.raises(NotInvitedError):
        world.sign_up.execute(uuid4(), "nadie@example.com")

    assert world.tenants.count() == 0
    assert world.profiles.profiles == {}


def test_the_invited_business_starts_its_wizard_after_the_business_step() -> None:
    world = World()
    tenant = world.create.execute(uuid4(), "Inmobiliaria Sur", "corredor", "owner@example.com")

    world.sign_up.execute(uuid4(), "owner@example.com")

    onboarding = world.onboardings.get(tenant.id)
    assert onboarding is not None
    assert onboarding.current_step == OnboardingStep.AGENT
    assert OnboardingStep.BUSINESS in onboarding.completed_steps
