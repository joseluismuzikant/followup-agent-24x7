from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from followup_core.tenancy.domain.agent_config import AgentConfig

from ..domain.runtime import BusinessContext


class AgentConfigSource(Protocol):
    def current(self, tenant_id: UUID) -> tuple[int, AgentConfig]:
        """The current version number (0 = product defaults) and its config."""
        ...

    def at_version(self, tenant_id: UUID, version: int) -> AgentConfig: ...


BusinessContextSource = Callable[[UUID], BusinessContext]
