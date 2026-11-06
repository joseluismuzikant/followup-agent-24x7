"""Configuración: business name and type, team hours and notification emails."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from followup_core.identity.domain.profile import Profile, Role
from followup_core.tenancy.application.tenant_settings import (
    GetTenantSettings,
    TenantSettingsView,
    UpdateTenantSettings,
)
from followup_core.tenancy.domain.errors import (
    InvalidBusinessTypeError,
    InvalidNotificationEmailError,
    InvalidTeamHoursError,
    InvalidTenantNameError,
    TenantNotFoundError,
    TenantSetupNotFoundError,
)
from followup_core.tenancy.domain.product import ProductDefinition
from pydantic import BaseModel

from followup_platform.routers.setup_schemas import (
    ScheduleBlockModel,
    hours_from_models,
    hours_to_models,
)

from ..auth import Auth
from ..http_errors import ApiError

GetSettingsFactory = Callable[..., GetTenantSettings]
UpdateSettingsFactory = Callable[..., UpdateTenantSettings]


class TenantSettingsRead(BaseModel):
    business_name: str
    business_type: str
    timezone: str
    business_hours: list[ScheduleBlockModel]
    notification_emails: list[str]


class TenantSettingsWrite(BaseModel):
    business_name: str
    business_type: str
    business_hours: list[ScheduleBlockModel]
    notification_emails: list[str]


def _settings_read(view: TenantSettingsView) -> TenantSettingsRead:
    return TenantSettingsRead(
        business_name=view.tenant.name,
        business_type=view.settings.business_type,
        timezone=view.settings.timezone,
        business_hours=hours_to_models(view.settings.team_hours),
        notification_emails=list(view.settings.notification_emails),
    )


def build_tenant_settings_router(
    auth: Auth,
    definition: ProductDefinition,
    get_factory: GetSettingsFactory,
    update_factory: UpdateSettingsFactory,
) -> APIRouter:
    router = APIRouter(tags=["tenant-settings"])

    @router.get("/tenant/settings", response_model=TenantSettingsRead)
    def get_settings(
        profile: Annotated[Profile, Depends(auth.current_profile)],
        use_case: Annotated[GetTenantSettings, Depends(get_factory)],
    ) -> TenantSettingsRead:
        try:
            return _settings_read(use_case.execute(profile.tenant_id))
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error

    @router.put("/tenant/settings", response_model=TenantSettingsRead)
    def update_settings(
        payload: TenantSettingsWrite,
        profile: Annotated[Profile, Depends(auth.require_role(Role.OWNER, Role.MANAGER))],
        use_case: Annotated[UpdateTenantSettings, Depends(update_factory)],
    ) -> TenantSettingsRead:
        try:
            view = use_case.execute(
                tenant_id=profile.tenant_id,
                business_name=payload.business_name,
                business_type=definition.parse_business_type(payload.business_type),
                team_hours=hours_from_models(payload.business_hours),
                notification_emails=tuple(payload.notification_emails),
            )
        except InvalidBusinessTypeError as error:
            raise ApiError(422, "business_type_invalid") from error
        except InvalidTenantNameError as error:
            raise ApiError(422, "tenant_name_invalid") from error
        except InvalidTeamHoursError as error:
            raise ApiError(422, "team_hours_invalid") from error
        except InvalidNotificationEmailError as error:
            raise ApiError(422, "notification_email_invalid") from error
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        except TenantSetupNotFoundError as error:
            raise ApiError(404, "setup_not_found") from error
        return _settings_read(view)

    return router
