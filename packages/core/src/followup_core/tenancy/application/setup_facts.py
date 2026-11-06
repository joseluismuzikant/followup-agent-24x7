from collections.abc import Callable
from uuid import UUID

FactProvider = Callable[[UUID], bool]


def not_yet(_tenant_id: UUID) -> bool:
    """Provider for facts whose feature has not been built yet."""
    return False


def always(_tenant_id: UUID) -> bool:
    """Provider for facts true for every signed-up business (the account exists)."""
    return True
