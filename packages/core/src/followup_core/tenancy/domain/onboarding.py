from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from uuid import UUID

from .errors import InvalidOnboardingStepError


def _position(steps: Sequence[str], step: str) -> int:
    try:
        return list(steps).index(step)
    except ValueError as error:
        raise InvalidOnboardingStepError(f"Unknown onboarding step '{step}'.") from error


@dataclass(frozen=True, slots=True)
class Onboarding:
    """Furthest wizard step reached by a tenant.

    The steps belong to the product (`ProductDefinition.onboarding_steps`); these rules are
    the same for every product: `current_step` only moves forward, revisiting an earlier step
    to edit it is just navigation and never uncompletes anything, and reaching the last step
    finishes the onboarding.
    """

    tenant_id: UUID
    current_step: str
    completed_steps: Mapping[str, datetime]
    finished_at: datetime | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_step", str(self.current_step))
        object.__setattr__(
            self,
            "completed_steps",
            MappingProxyType({str(step): at for step, at in self.completed_steps.items()}),
        )

    @classmethod
    def start(
        cls, tenant_id: UUID, now: datetime, steps: Sequence[str], first_step: str
    ) -> "Onboarding":
        """Sign-up completes every step before `first_step` and lands on it."""
        position = _position(steps, first_step)
        return cls(
            tenant_id=tenant_id,
            current_step=first_step,
            completed_steps={step: now for step in list(steps)[:position]},
            finished_at=None,
        )

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    def is_reachable(self, step: str, steps: Sequence[str]) -> bool:
        return _position(steps, step) <= _position(steps, self.current_step)

    def advance_to(self, step: str, now: datetime, steps: Sequence[str]) -> "Onboarding":
        """Move to `step`, which must be the next step or one already reached.

        Targeting an already reached step changes nothing, so retries are safe.
        """
        if self.is_reachable(step, steps):
            return self
        if _position(steps, step) != _position(steps, self.current_step) + 1:
            raise InvalidOnboardingStepError(f"Cannot move from '{self.current_step}' to '{step}'.")

        completed = dict(self.completed_steps)
        completed.setdefault(self.current_step, now)
        finished_at = self.finished_at
        if step == steps[-1]:
            completed[step] = now
            finished_at = now
        return Onboarding(
            tenant_id=self.tenant_id,
            current_step=step,
            completed_steps=completed,
            finished_at=finished_at,
        )
