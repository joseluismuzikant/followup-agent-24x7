from collections.abc import Sequence
from typing import Protocol

from .tenant import Tenant


class TenantRepository(Protocol):
    def add(self, tenant: Tenant) -> None: ...

    def list_page(self, page: int, limit: int) -> Sequence[Tenant]: ...

    def count(self) -> int: ...

    def slug_exists(self, slug: str) -> bool: ...
