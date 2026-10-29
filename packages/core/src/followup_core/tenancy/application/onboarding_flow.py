from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from ..domain.errors import TenantSetupNotFoundError
from ..domain.onboarding import Onboarding, OnboardingStep
from ..domain.onboarding_repository import OnboardingRepository
from ..domain.setup_checklist import SetupChecklist
from .get_setup_checklist import GetSetupChecklist


@dataclass(frozen=True, slots=True)
class OnboardingState:
    onboarding: Onboarding
    checklist: SetupChecklist


class GetOnboarding:
    def __init__(
        self,
        onboardings: OnboardingRepository,
        checklist: GetSetupChecklist,
    ) -> None:
        self._onboardings = onboardings
        self._checklist = checklist

    def execute(self, tenant_id: UUID) -> OnboardingState:
        onboarding = self._onboardings.get(tenant_id)
        if onboarding is None:
            raise TenantSetupNotFoundError("The tenant has no onboarding record.")
        return OnboardingState(onboarding, self._checklist.execute(tenant_id))


class AdvanceOnboarding:
    def __init__(
        self,
        onboardings: OnboardingRepository,
        checklist: GetSetupChecklist,
    ) -> None:
        self._onboardings = onboardings
        self._checklist = checklist

    def execute(self, tenant_id: UUID, to_step: OnboardingStep) -> OnboardingState:
        onboarding = self._onboardings.get(tenant_id)
        if onboarding is None:
            raise TenantSetupNotFoundError("The tenant has no onboarding record.")

        advanced = onboarding.advance_to(to_step, datetime.now(UTC))
        if advanced is not onboarding:
            self._onboardings.save(advanced)
        return OnboardingState(advanced, self._checklist.execute(tenant_id))
