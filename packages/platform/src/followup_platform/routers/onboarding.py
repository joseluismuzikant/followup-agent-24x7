"""The onboarding wizard's progress and the setup checklist, for any product (the steps and
the checklist's facts come from the product)."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Annotated, Any

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
from followup_core.tenancy.domain.product import ProductDefinition
from followup_core.tenancy.domain.setup_checklist import SetupChecklist
from pydantic import BaseModel, create_model

from ..auth import Auth
from ..http_errors import ApiError

GetOnboardingFactory = Callable[..., GetOnboarding]
AdvanceOnboardingFactory = Callable[..., AdvanceOnboarding]


class ChecklistItemRead(BaseModel):
    key: str
    done: bool


class CompletedStepRead(BaseModel):
    step: str
    completed_at: datetime


class AdvanceRequest(BaseModel):
    to_step: str


def onboarding_models(facts: Sequence[str]) -> tuple[type[BaseModel], type[BaseModel]]:
    """The product's checklist and onboarding read models. `facts` names every fact of the
    product (each a bool), so the OpenAPI schema lists them."""
    fields: dict[str, Any] = {name: (bool, ...) for name in facts}
    facts_model = create_model("SetupFactsRead", **fields)
    checklist_model = create_model(
        "ChecklistRead",
        items=(list[ChecklistItemRead], ...),
        ready_count=(int, ...),
        total=(int, ...),
        facts=(facts_model, ...),
    )
    onboarding_model = create_model(
        "OnboardingRead",
        current_step=(str, ...),
        completed_steps=(list[CompletedStepRead], ...),
        finished=(bool, ...),
        checklist=(checklist_model, ...),
    )
    return checklist_model, onboarding_model


def checklist_read(checklist: SetupChecklist, model: type[BaseModel]) -> BaseModel:
    return model(
        items=[ChecklistItemRead(key=item.key, done=item.done) for item in checklist.items],
        ready_count=checklist.ready_count,
        total=checklist.total,
        facts=dict(checklist.facts),
    )


def build_onboarding_router(
    auth: Auth,
    definition: ProductDefinition,
    facts: Sequence[str],
    get_onboarding_factory: GetOnboardingFactory,
    advance_onboarding_factory: AdvanceOnboardingFactory,
) -> APIRouter:
    router = APIRouter(tags=["onboarding"])
    checklist_model, onboarding_model = onboarding_models(facts)
    steps = tuple(definition.onboarding_steps)

    def read(state: OnboardingState) -> BaseModel:
        onboarding = state.onboarding
        return onboarding_model(
            current_step=onboarding.current_step,
            completed_steps=[
                CompletedStepRead(step=step, completed_at=onboarding.completed_steps[step])
                for step in steps
                if step in onboarding.completed_steps
            ],
            finished=onboarding.finished,
            checklist=checklist_read(state.checklist, checklist_model),
        )

    @router.get("/onboarding", response_model=onboarding_model)
    def get_onboarding(
        profile: Annotated[Profile, Depends(auth.current_profile)],
        use_case: Annotated[GetOnboarding, Depends(get_onboarding_factory)],
    ) -> Any:
        try:
            return read(use_case.execute(profile.tenant_id))
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error

    @router.post("/onboarding/advance", response_model=onboarding_model)
    def advance_onboarding(
        payload: AdvanceRequest,
        profile: Annotated[Profile, Depends(auth.require_role(Role.OWNER, Role.MANAGER))],
        use_case: Annotated[AdvanceOnboarding, Depends(advance_onboarding_factory)],
    ) -> Any:
        if payload.to_step not in steps:
            raise ApiError(422, "onboarding_step_invalid")
        try:
            return read(use_case.execute(profile.tenant_id, payload.to_step))
        except InvalidOnboardingStepError as error:
            raise ApiError(422, "onboarding_step_invalid") from error
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error

    return router
