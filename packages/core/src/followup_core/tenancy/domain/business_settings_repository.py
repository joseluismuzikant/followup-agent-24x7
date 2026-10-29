from typing import Protocol
from uuid import UUID

from .business_settings import BusinessSettings


class BusinessSettingsRepository(Protocol):
    def get(self, tenant_id: UUID) -> BusinessSettings | None: ...

    def add(self, settings: BusinessSettings) -> None: ...

    def save(self, settings: BusinessSettings) -> None: ...
