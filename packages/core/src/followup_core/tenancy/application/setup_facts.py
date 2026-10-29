from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

FactProvider = Callable[[UUID], bool]


def not_yet(_tenant_id: UUID) -> bool:
    """Provider for facts whose feature has not been built yet."""
    return False


@dataclass(frozen=True, slots=True)
class SetupFactProviders:
    """Facts owned by later days. Each day swaps in its own provider."""

    agent_tested: FactProvider = not_yet
    whatsapp_connected: FactProvider = not_yet
    own_properties: FactProvider = not_yet
    meta_business_verified: FactProvider = not_yet
