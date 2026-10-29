from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from followup_core.identity.domain.profile import Profile, Role
from followup_core.tenancy.application.onboarding_flow import (
    AdvanceOnboarding,
    GetOnboarding,
    OnboardingState,
)
from followup_core.tenancy.domain.errors import (
    InvalidOnboardingStepError,
    TenantSetupNotFoundError,
)
from followup_core.tenancy.domain.onboarding import STEP_ORDER, OnboardingStep
from followup_core.tenancy.domain.setup_checklist import SetupChecklist
from pydantic import BaseModel

from .auth import current_profile, require_role
from .http_errors import ApiError

GetOnboardingFactory = Callable[..., GetOnboarding]
AdvanceOnboardingFactory = Callable[..., AdvanceOnboarding]


class ChecklistItemRead(BaseModel):
    key: str
    done: bool


class SetupFactsRead(BaseModel):
    account_created: bool
    agent_configured: bool
    agent_tested: bool
    whatsapp_connected: bool
    own_properties: bool
    meta_business_verified: bool


class ChecklistRead(BaseModel):
    items: list[ChecklistItemRead]
    ready_count: int
    total: int
    facts: SetupFactsRead


class CompletedStepRead(BaseModel):
    step: str
    completed_at: datetime


class OnboardingRead(BaseModel):
    current_step: str
    completed_steps: list[CompletedStepRead]
    finished: bool
    checklist: ChecklistRead


class AdvanceRequest(BaseModel):
    to_step: str


def checklist_read(checklist: SetupChecklist) -> ChecklistRead:
    facts = checklist.facts
    return ChecklistRead(
        items=[ChecklistItemRead(key=item.key.value, done=item.done) for item in checklist.items],
        ready_count=checklist.ready_count,
        total=checklist.total,
        facts=SetupFactsRead(
            account_created=facts.account_created,
            agent_configured=facts.agent_configured,
            agent_tested=facts.agent_tested,
            whatsapp_connected=facts.whatsapp_connected,
            own_properties=facts.own_properties,
            meta_business_verified=facts.meta_business_verified,
        ),
    )


def _onboarding_read(state: OnboardingState) -> OnboardingRead:
    onboarding = state.onboarding
    return OnboardingRead(
        current_step=onboarding.current_step.value,
        completed_steps=[
            CompletedStepRead(step=step.value, completed_at=onboarding.completed_steps[step])
            for step in STEP_ORDER
            if step in onboarding.completed_steps
        ],
        finished=onboarding.finished,
        checklist=checklist_read(state.checklist),
    )


def build_onboarding_router(
    get_onboarding_factory: GetOnboardingFactory,
    advance_onboarding_factory: AdvanceOnboardingFactory,
) -> APIRouter:
    router = APIRouter(tags=["onboarding"])

    @router.get("/onboarding", response_model=OnboardingRead)
    def get_onboarding(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[GetOnboarding, Depends(get_onboarding_factory)],
    ) -> OnboardingRead:
        try:
            return _onboarding_read(use_case.execute(profile.tenant_id))
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error

    @router.post("/onboarding/advance", response_model=OnboardingRead)
    def advance_onboarding(
        payload: AdvanceRequest,
        profile: Annotated[Profile, Depends(require_role(Role.OWNER, Role.MANAGER))],
        use_case: Annotated[AdvanceOnboarding, Depends(advance_onboarding_factory)],
    ) -> OnboardingRead:
        try:
            step = OnboardingStep(payload.to_step)
        except ValueError as error:
            raise ApiError(422, "onboarding_step_invalid") from error
        try:
            return _onboarding_read(use_case.execute(profile.tenant_id, step))
        except InvalidOnboardingStepError as error:
            raise ApiError(422, "onboarding_step_invalid") from error
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error

    return router
