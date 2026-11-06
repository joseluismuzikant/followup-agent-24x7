from dataclasses import dataclass
from typing import Protocol

from ..domain.agent_config import AgentConfig
from ..domain.business_settings import ScheduleBlock


class BusinessDefaults(Protocol):
    """What sign-up needs to create a business's settings."""

    @property
    def team_hours(self) -> tuple[ScheduleBlock, ...]: ...

    @property
    def timezone(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BusinessSettingsDefaults:
    """Defaults for a product without an agent to configure (yet)."""

    team_hours: tuple[ScheduleBlock, ...]
    timezone: str


@dataclass(frozen=True, slots=True)
class SetupDefaults:
    """What a new tenant starts with. Each product decides these values."""

    agent_config: AgentConfig
    team_hours: tuple[ScheduleBlock, ...]
    timezone: str
