from dataclasses import dataclass
from uuid import UUID

from ..domain.business_settings import (
    BusinessSettings,
    BusinessType,
    ScheduleBlock,
)
from ..domain.business_settings_repository import BusinessSettingsRepository
from ..domain.errors import TenantNotFoundError, TenantSetupNotFoundError
from ..domain.tenant import Tenant
from ..domain.tenant_repository import TenantRepository


@dataclass(frozen=True, slots=True)
class TenantSettingsView:
    tenant: Tenant
    settings: BusinessSettings


class GetTenantSettings:
    def __init__(
        self,
        tenants: TenantRepository,
        settings: BusinessSettingsRepository,
    ) -> None:
        self._tenants = tenants
        self._settings = settings

    def execute(self, tenant_id: UUID) -> TenantSettingsView:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' does not exist.")
        settings = self._settings.get(tenant_id)
        if settings is None:
            raise TenantSetupNotFoundError("The tenant has no business settings.")
        return TenantSettingsView(tenant, settings)


class UpdateTenantSettings:
    def __init__(
        self,
        tenants: TenantRepository,
        settings: BusinessSettingsRepository,
    ) -> None:
        self._tenants = tenants
        self._settings = settings
        self._get = GetTenantSettings(tenants, settings)

    def execute(
        self,
        tenant_id: UUID,
        business_name: str,
        business_type: BusinessType,
        team_hours: tuple[ScheduleBlock, ...],
        notification_emails: tuple[str, ...],
    ) -> TenantSettingsView:
        current = self._get.execute(tenant_id)

        renamed = current.tenant.rename(business_name)
        updated = current.settings.with_changes(
            business_type=business_type,
            team_hours=team_hours,
            notification_emails=notification_emails,
        )
        if renamed != current.tenant:
            self._tenants.save(renamed)
        if updated != current.settings:
            self._settings.save(updated)
        return TenantSettingsView(renamed, updated)
