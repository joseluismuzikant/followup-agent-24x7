from dataclasses import dataclass

from ..domain.agent_config import AgentConfig
from ..domain.business_settings import ScheduleBlock


@dataclass(frozen=True, slots=True)
class SetupDefaults:
    """What a new tenant starts with. Each product decides these values."""

    agent_config: AgentConfig
    team_hours: tuple[ScheduleBlock, ...]
    timezone: str
