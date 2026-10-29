from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from followup_core.identity.domain.profile import Profile, Role
from followup_core.tenancy.application.agent_setup import (
    AgentSetup,
    GetAgentSetup,
    ListAgentConfigVersions,
    SaveAgentSetup,
)
from followup_core.tenancy.domain.errors import (
    AgentConfigConflictError,
    InvalidAgentNameError,
    InvalidNotificationEmailError,
    InvalidQuestionsError,
    InvalidTeamHoursError,
    TenantSetupNotFoundError,
)
from pydantic import BaseModel

from .auth import current_profile, require_role
from .http_errors import ApiError
from .setup_schemas import (
    AgentConfigInputModel,
    AgentConfigModel,
    ScheduleBlockModel,
    config_to_model,
    draft_from_model,
    hours_from_models,
    hours_to_models,
)

GetAgentSetupFactory = Callable[..., GetAgentSetup]
SaveAgentSetupFactory = Callable[..., SaveAgentSetup]
ListVersionsFactory = Callable[..., ListAgentConfigVersions]


class AgentSetupRead(BaseModel):
    config: AgentConfigModel
    version: int
    updated_at: datetime | None
    business_hours: list[ScheduleBlockModel]
    notification_emails: list[str]
    defaults: AgentConfigModel


class AgentSetupWrite(BaseModel):
    config: AgentConfigInputModel
    business_hours: list[ScheduleBlockModel]
    notification_emails: list[str]


class AgentVersionRead(BaseModel):
    version: int
    created_at: datetime
    author_email: str | None


def _agent_setup_read(setup: AgentSetup) -> AgentSetupRead:
    return AgentSetupRead(
        config=config_to_model(setup.config),
        version=setup.version,
        updated_at=setup.updated_at,
        business_hours=hours_to_models(setup.team_hours),
        notification_emails=list(setup.notification_emails),
        defaults=config_to_model(setup.defaults),
    )


def build_agent_setup_router(
    get_factory: GetAgentSetupFactory,
    save_factory: SaveAgentSetupFactory,
    list_versions_factory: ListVersionsFactory,
) -> APIRouter:
    router = APIRouter(tags=["agent-setup"])

    @router.get("/agent-setup", response_model=AgentSetupRead)
    def get_agent_setup(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[GetAgentSetup, Depends(get_factory)],
    ) -> AgentSetupRead:
        try:
            return _agent_setup_read(use_case.execute(profile.tenant_id))
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error

    @router.put("/agent-setup", response_model=AgentSetupRead)
    def save_agent_setup(
        payload: AgentSetupWrite,
        profile: Annotated[Profile, Depends(require_role(Role.OWNER, Role.MANAGER))],
        use_case: Annotated[SaveAgentSetup, Depends(save_factory)],
    ) -> AgentSetupRead:
        try:
            setup = use_case.execute(
                tenant_id=profile.tenant_id,
                profile_id=profile.id,
                draft=draft_from_model(payload.config),
                team_hours=hours_from_models(payload.business_hours),
                notification_emails=tuple(payload.notification_emails),
            )
        except InvalidAgentNameError as error:
            raise ApiError(422, "agent_name_invalid") from error
        except InvalidQuestionsError as error:
            raise ApiError(422, "questions_invalid") from error
        except InvalidTeamHoursError as error:
            raise ApiError(422, "team_hours_invalid") from error
        except InvalidNotificationEmailError as error:
            raise ApiError(422, "notification_email_invalid") from error
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error
        except AgentConfigConflictError as error:
            raise ApiError(409, "agent_setup_conflict") from error
        return _agent_setup_read(setup)

    @router.get("/agent-setup/versions", response_model=list[AgentVersionRead])
    def list_versions(
        profile: Annotated[Profile, Depends(current_profile)],
        use_case: Annotated[ListAgentConfigVersions, Depends(list_versions_factory)],
    ) -> list[AgentVersionRead]:
        return [
            AgentVersionRead(
                version=item.version,
                created_at=item.created_at,
                author_email=item.author_email,
            )
            for item in use_case.execute(profile.tenant_id, limit=20)
        ]

    return router
