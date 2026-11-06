from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from followup_core.tenancy.application.get_setup_checklist import GetSetupChecklist
from followup_core.tenancy.application.onboarding_flow import AdvanceOnboarding, GetOnboarding
from followup_core.tenancy.application.setup_facts import always, not_yet
from followup_core.tenancy.domain.errors import (
    InvalidOnboardingStepError,
    TenantSetupNotFoundError,
)
from followup_core.tenancy.domain.onboarding import Onboarding
from tenancy_fakes import STEPS, InMemoryOnboardingRepository, OnboardingStep

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def test_start_completes_business_and_lands_on_agent() -> None:
    onboarding = Onboarding.start(uuid4(), NOW, STEPS, OnboardingStep.AGENT)

    assert onboarding.current_step == OnboardingStep.AGENT
    assert set(onboarding.completed_steps) == {OnboardingStep.BUSINESS}
    assert onboarding.finished is False


def test_advance_moves_one_step_and_completes_the_previous() -> None:
    onboarding = Onboarding.start(uuid4(), NOW, STEPS, OnboardingStep.AGENT)
    later = NOW + timedelta(minutes=1)

    advanced = onboarding.advance_to(OnboardingStep.TRY, later, STEPS)

    assert advanced.current_step == OnboardingStep.TRY
    assert advanced.completed_steps[OnboardingStep.AGENT] == later
    assert advanced.completed_steps[OnboardingStep.BUSINESS] == NOW


def test_cannot_skip_steps() -> None:
    with pytest.raises(InvalidOnboardingStepError):
        Onboarding.start(uuid4(), NOW, STEPS, OnboardingStep.AGENT).advance_to(
            OnboardingStep.WHATSAPP, NOW, STEPS
        )


def test_going_back_changes_nothing() -> None:
    onboarding = Onboarding.start(uuid4(), NOW, STEPS, OnboardingStep.AGENT).advance_to(
        OnboardingStep.TRY, NOW, STEPS
    )

    assert onboarding.advance_to(OnboardingStep.AGENT, NOW, STEPS) is onboarding
    assert onboarding.advance_to(OnboardingStep.TRY, NOW, STEPS) is onboarding
    assert onboarding.is_reachable(OnboardingStep.BUSINESS, STEPS)
    assert not onboarding.is_reachable(OnboardingStep.WHATSAPP, STEPS)


def test_reaching_done_finishes_onboarding() -> None:
    onboarding = Onboarding.start(uuid4(), NOW, STEPS, OnboardingStep.AGENT)
    for step in (OnboardingStep.TRY, OnboardingStep.WHATSAPP, OnboardingStep.DONE):
        onboarding = onboarding.advance_to(step, NOW, STEPS)

    assert onboarding.finished_at == NOW
    assert onboarding.current_step == OnboardingStep.DONE
    assert set(onboarding.completed_steps) == set(OnboardingStep)


def _use_cases():
    onboardings = InMemoryOnboardingRepository()
    checklist = GetSetupChecklist(
        [("account", "account_created"), ("agent", "agent_configured")],
        {"account_created": always, "agent_configured": not_yet},
    )
    return (
        onboardings,
        GetOnboarding(onboardings, checklist),
        AdvanceOnboarding(onboardings, checklist, STEPS),
    )


def test_advance_use_case_persists_and_returns_checklist() -> None:
    onboardings, _, advance = _use_cases()
    tenant_id = uuid4()
    onboardings.add(Onboarding.start(tenant_id, NOW, STEPS, OnboardingStep.AGENT))

    state = advance.execute(tenant_id, OnboardingStep.TRY)

    saved = onboardings.get(tenant_id)
    assert saved is not None
    assert saved.current_step == OnboardingStep.TRY
    assert state.checklist.total == 2


def test_use_cases_require_an_onboarding_record() -> None:
    _, get, advance = _use_cases()

    with pytest.raises(TenantSetupNotFoundError):
        get.execute(uuid4())
    with pytest.raises(TenantSetupNotFoundError):
        advance.execute(uuid4(), OnboardingStep.TRY)


def test_each_product_defines_its_own_steps() -> None:
    steps = ("negocio", "facturas", "recordatorios", "conectar", "listo")
    onboarding = Onboarding.start(uuid4(), NOW, steps, "facturas")

    assert dict(onboarding.completed_steps) == {"negocio": NOW}
    for step in steps[2:]:
        onboarding = onboarding.advance_to(step, NOW, steps)
    assert onboarding.finished_at == NOW
    with pytest.raises(InvalidOnboardingStepError):
        onboarding.advance_to("agent", NOW, steps)
