from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

from .errors import InvalidOnboardingStepError


class OnboardingStep(StrEnum):
    BUSINESS = "business"
    AGENT = "agent"
    TRY = "try"
    WHATSAPP = "whatsapp"
    DONE = "done"


STEP_ORDER: tuple[OnboardingStep, ...] = tuple(OnboardingStep)


def _position(step: OnboardingStep) -> int:
    return STEP_ORDER.index(step)


@dataclass(frozen=True, slots=True)
class Onboarding:
    """Furthest wizard step reached by a tenant.

    `current_step` only moves forward. Revisiting an earlier step to edit it is just
    navigation and never uncompletes anything.
    """

    tenant_id: UUID
    current_step: OnboardingStep
    completed_steps: Mapping[OnboardingStep, datetime]
    finished_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "completed_steps", MappingProxyType(dict(self.completed_steps)))

    @classmethod
    def start(cls, tenant_id: UUID, now: datetime) -> "Onboarding":
        """Sign-up completes the business step and lands on the agent step."""
        return cls(
            tenant_id=tenant_id,
            current_step=OnboardingStep.AGENT,
            completed_steps={OnboardingStep.BUSINESS: now},
            finished_at=None,
        )

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    def is_reachable(self, step: OnboardingStep) -> bool:
        return _position(step) <= _position(self.current_step)

    def advance_to(self, step: OnboardingStep, now: datetime) -> "Onboarding":
        """Move to `step`, which must be the next step or one already reached.

        Targeting an already reached step changes nothing, so retries are safe.
        """
        if self.is_reachable(step):
            return self
        if _position(step) != _position(self.current_step) + 1:
            raise InvalidOnboardingStepError(f"Cannot move from '{self.current_step}' to '{step}'.")

        completed = dict(self.completed_steps)
        completed.setdefault(self.current_step, now)
        finished_at = self.finished_at
        if step is OnboardingStep.DONE:
            completed[OnboardingStep.DONE] = now
            finished_at = now
        return Onboarding(
            tenant_id=self.tenant_id,
            current_step=step,
            completed_steps=completed,
            finished_at=finished_at,
        )
