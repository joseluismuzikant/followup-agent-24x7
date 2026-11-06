from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 5000

# The template's columns, in order (Spanish: the business fills them in).
COLUMNS = (
    "cliente",
    "detalle_cliente",
    "cuit",
    "contacto",
    "whatsapp",
    "email",
    "tipo",
    "punto_venta",
    "numero",
    "fecha_emision",
    "vencimiento",
    "monto",
    "moneda",
    "descripcion",
    "estado",
    "fecha_pago",
    "medio_pago",
)
REQUIRED_COLUMNS = ("cliente", "tipo", "punto_venta", "numero", "vencimiento", "monto")


@dataclass(frozen=True, slots=True)
class FailedRow:
    row: int  # as the spreadsheet numbers it: the header is row 1
    error: str  # "Fila 7: el CUIT no es válido."
    values: Mapping[str, str]  # the original cells, by original column name


@dataclass(frozen=True, slots=True)
class InvoiceImport:
    id: UUID
    tenant_id: UUID
    created_by_profile_id: UUID | None
    file_name: str
    total: int
    created: int
    updated: int
    # Valid rows left as they were (an invoice already paid or cancelled).
    skipped: int
    columns: Sequence[str]
    failed_rows: Sequence[FailedRow]
    warnings: Sequence[str]
    created_at: datetime

    @property
    def failed(self) -> int:
        return len(self.failed_rows)

    @property
    def imported(self) -> int:
        return self.created + self.updated


class InvoiceImportRepository(Protocol):
    def add(self, record: InvoiceImport) -> None: ...

    def get(self, tenant_id: UUID, import_id: UUID) -> InvoiceImport | None: ...
