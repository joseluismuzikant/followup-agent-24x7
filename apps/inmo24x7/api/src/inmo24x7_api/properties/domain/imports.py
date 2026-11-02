from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 2000


@dataclass(frozen=True, slots=True)
class Table:
    """A spreadsheet as read from the file: header row and data rows, all as text."""

    columns: Sequence[str]
    rows: Sequence[Sequence[str]]


@dataclass(frozen=True, slots=True)
class FailedRow:
    row: int  # as the spreadsheet numbers it: the header is row 1
    error: str  # "Fila 12: falta el precio."
    values: Mapping[str, str]  # the original cells, by original column name


@dataclass(frozen=True, slots=True)
class PropertyImport:
    id: UUID
    tenant_id: UUID
    created_by_profile_id: UUID | None
    file_name: str
    total: int
    created: int
    updated: int
    columns: Sequence[str]
    failed_rows: Sequence[FailedRow]
    created_at: datetime

    @property
    def failed(self) -> int:
        return len(self.failed_rows)

    @property
    def imported(self) -> int:
        return self.created + self.updated
