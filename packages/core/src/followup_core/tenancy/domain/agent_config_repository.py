from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .agent_config import AgentConfig


@dataclass(frozen=True, slots=True)
class AgentConfigVersion:
    tenant_id: UUID
    version: int
    created_at: datetime
    created_by_profile_id: UUID
    config: AgentConfig


class AgentConfigRepository(Protocol):
    def latest(self, tenant_id: UUID) -> AgentConfigVersion | None: ...

    def get_version(self, tenant_id: UUID, version: int) -> AgentConfigVersion | None: ...

    def question_keys(self, tenant_id: UUID) -> set[str]:
        """Every question key used in any version of this tenant's config."""
        ...

    def add_version(self, version: AgentConfigVersion) -> None:
        """Raises AgentConfigConflictError when the version number is already taken."""
        ...

    def list_versions(self, tenant_id: UUID, limit: int) -> Sequence[AgentConfigVersion]:
        """Newest first."""
        ...
