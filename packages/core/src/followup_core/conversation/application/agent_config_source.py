from uuid import UUID

from followup_core.tenancy.application.defaults import SetupDefaults
from followup_core.tenancy.domain.agent_config import AgentConfig
from followup_core.tenancy.domain.agent_config_repository import AgentConfigRepository


class VersionedAgentConfigSource:
    """Reads pinned agent configs from Tenancy. Version 0 means the product defaults."""

    def __init__(self, agent_configs: AgentConfigRepository, defaults: SetupDefaults) -> None:
        self._agent_configs = agent_configs
        self._defaults = defaults

    def current(self, tenant_id: UUID) -> tuple[int, AgentConfig]:
        latest = self._agent_configs.latest(tenant_id)
        if latest is None:
            return 0, self._defaults.agent_config
        return latest.version, latest.config

    def at_version(self, tenant_id: UUID, version: int) -> AgentConfig:
        if version == 0:
            return self._defaults.agent_config
        saved = self._agent_configs.get_version(tenant_id, version)
        if saved is None:
            raise LookupError(f"Agent config version {version} does not exist.")
        return saved.config
