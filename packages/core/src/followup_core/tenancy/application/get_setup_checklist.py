from uuid import UUID

from ..domain.agent_config_repository import AgentConfigRepository
from ..domain.setup_checklist import SetupChecklist, SetupFacts
from .setup_facts import SetupFactProviders


class GetSetupChecklist:
    def __init__(
        self,
        agent_configs: AgentConfigRepository,
        providers: SetupFactProviders,
    ) -> None:
        self._agent_configs = agent_configs
        self._providers = providers

    def execute(self, tenant_id: UUID) -> SetupChecklist:
        return SetupChecklist.from_facts(
            SetupFacts(
                account_created=True,
                agent_configured=self._agent_configs.latest(tenant_id) is not None,
                agent_tested=self._providers.agent_tested(tenant_id),
                whatsapp_connected=self._providers.whatsapp_connected(tenant_id),
                own_properties=self._providers.own_properties(tenant_id),
                meta_business_verified=self._providers.meta_business_verified(tenant_id),
            )
        )
