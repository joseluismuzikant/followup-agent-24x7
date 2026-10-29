from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from followup_core.identity.domain.profile_repository import ProfileRepository

from ..domain.agent_config import AgentConfig
from ..domain.agent_config_repository import AgentConfigRepository, AgentConfigVersion
from ..domain.business_settings import ScheduleBlock
from ..domain.business_settings_repository import BusinessSettingsRepository
from ..domain.errors import TenantSetupNotFoundError
from .defaults import SetupDefaults


@dataclass(frozen=True, slots=True)
class AgentSetup:
    config: AgentConfig
    version: int
    updated_at: datetime | None
    team_hours: tuple[ScheduleBlock, ...]
    notification_emails: tuple[str, ...]
    defaults: AgentConfig


@dataclass(frozen=True, slots=True)
class AgentConfigVersionSummary:
    version: int
    created_at: datetime
    author_email: str | None


class GetAgentSetup:
    def __init__(
        self,
        agent_configs: AgentConfigRepository,
        settings: BusinessSettingsRepository,
        defaults: SetupDefaults,
    ) -> None:
        self._agent_configs = agent_configs
        self._settings = settings
        self._defaults = defaults

    def execute(self, tenant_id: UUID) -> AgentSetup:
        settings = self._settings.get(tenant_id)
        if settings is None:
            raise TenantSetupNotFoundError("The tenant has no business settings.")

        latest = self._agent_configs.latest(tenant_id)
        return AgentSetup(
            config=latest.config if latest else self._defaults.agent_config,
            version=latest.version if latest else 0,
            updated_at=latest.created_at if latest else None,
            team_hours=settings.team_hours,
            notification_emails=settings.notification_emails,
            defaults=self._defaults.agent_config,
        )


class SaveAgentSetup:
    """Saves the agent configuration and the team hours/emails as one unit.

    The caller's transaction makes the two writes atomic. A new agent version is only
    created when the configuration actually changed.
    """

    def __init__(
        self,
        agent_configs: AgentConfigRepository,
        settings: BusinessSettingsRepository,
        defaults: SetupDefaults,
    ) -> None:
        self._agent_configs = agent_configs
        self._settings = settings
        self._get = GetAgentSetup(agent_configs, settings, defaults)

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        config: AgentConfig,
        team_hours: tuple[ScheduleBlock, ...],
        notification_emails: tuple[str, ...],
    ) -> AgentSetup:
        current_settings = self._settings.get(tenant_id)
        if current_settings is None:
            raise TenantSetupNotFoundError("The tenant has no business settings.")

        new_settings = current_settings.with_changes(
            team_hours=team_hours,
            notification_emails=notification_emails,
        )
        latest = self._agent_configs.latest(tenant_id)
        if latest is None or latest.config != config:
            self._agent_configs.add_version(
                AgentConfigVersion(
                    tenant_id=tenant_id,
                    version=(latest.version if latest else 0) + 1,
                    created_at=datetime.now(UTC),
                    created_by_profile_id=profile_id,
                    config=config,
                )
            )
        if new_settings != current_settings:
            self._settings.save(new_settings)

        return self._get.execute(tenant_id)


class ListAgentConfigVersions:
    def __init__(
        self,
        agent_configs: AgentConfigRepository,
        profiles: ProfileRepository,
    ) -> None:
        self._agent_configs = agent_configs
        self._profiles = profiles

    def execute(self, tenant_id: UUID, limit: int = 20) -> Sequence[AgentConfigVersionSummary]:
        versions = self._agent_configs.list_versions(tenant_id, limit)
        emails: dict[UUID, str | None] = {}
        for version in versions:
            author_id = version.created_by_profile_id
            if author_id not in emails:
                profile = self._profiles.get_by_id(author_id)
                emails[author_id] = profile.email if profile else None
        return [
            AgentConfigVersionSummary(
                version=version.version,
                created_at=version.created_at,
                author_email=emails[version.created_by_profile_id],
            )
            for version in versions
        ]
