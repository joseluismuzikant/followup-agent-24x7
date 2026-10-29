from typing import Protocol
from uuid import UUID

from .onboarding import Onboarding


class OnboardingRepository(Protocol):
    def get(self, tenant_id: UUID) -> Onboarding | None: ...

    def add(self, onboarding: Onboarding) -> None: ...

    def save(self, onboarding: Onboarding) -> None: ...
