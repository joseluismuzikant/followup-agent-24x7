from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from .imports import PropertyImport
from .property import Operation, Property, PropertyStatus


@dataclass(frozen=True, slots=True)
class PropertyFilters:
    search: str | None = None  # address or zone, accent- and case-insensitive
    operation: Operation | None = None
    status: PropertyStatus | None = None


@dataclass(frozen=True, slots=True)
class PropertyRow:
    property: Property
    inquiries: int


@dataclass(frozen=True, slots=True)
class PropertyPage:
    items: Sequence[PropertyRow]
    total: int
    page: int
    page_size: int


class PropertyRepository(Protocol):
    def get(self, tenant_id: UUID, property_id: UUID) -> Property | None: ...

    def get_by_link(self, tenant_id: UUID, link: str) -> Property | None: ...

    def add(self, item: Property) -> None: ...

    def update(self, item: Property) -> None: ...

    def list(
        self, tenant_id: UUID, filters: PropertyFilters, page: int, page_size: int
    ) -> PropertyPage: ...

    def published(self, tenant_id: UUID) -> Sequence[Property]: ...

    def has_any(self, tenant_id: UUID) -> bool: ...

    def has_published(self, tenant_id: UUID) -> bool: ...


class PropertyImportRepository(Protocol):
    def add(self, record: PropertyImport) -> None: ...

    def get(self, tenant_id: UUID, import_id: UUID) -> PropertyImport | None: ...
