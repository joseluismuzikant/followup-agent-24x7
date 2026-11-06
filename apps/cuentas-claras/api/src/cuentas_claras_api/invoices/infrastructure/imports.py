from uuid import UUID

from followup_platform.tables import TableFileInvalidError, read_table
from sqlalchemy.orm import Session

from ..domain.errors import ImportFileInvalidError
from ..domain.imports import MAX_IMPORT_ROWS, FailedRow, InvoiceImport
from .models import InvoiceImportModel


def read_invoice_table(file_name: str, content: bytes) -> tuple[list[str], list[list[str]]]:
    try:
        table = read_table(file_name, content, MAX_IMPORT_ROWS)
    except TableFileInvalidError as error:
        raise ImportFileInvalidError(str(error)) from error
    return list(table.columns), [list(row) for row in table.rows]


class SqlAlchemyInvoiceImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: InvoiceImport) -> None:
        self._session.add(
            InvoiceImportModel(
                id=record.id,
                tenant_id=record.tenant_id,
                created_by_profile_id=record.created_by_profile_id,
                file_name=record.file_name,
                total=record.total,
                created=record.created,
                updated=record.updated,
                skipped=record.skipped,
                columns=list(record.columns),
                failed_rows=[
                    {"row": row.row, "error": row.error, "values": dict(row.values)}
                    for row in record.failed_rows
                ],
                warnings=list(record.warnings),
                created_at=record.created_at,
            )
        )
        self._session.flush()

    def get(self, tenant_id: UUID, import_id: UUID) -> InvoiceImport | None:
        model = self._session.get(InvoiceImportModel, import_id)
        if model is None or model.tenant_id != tenant_id:
            return None
        return InvoiceImport(
            id=model.id,
            tenant_id=model.tenant_id,
            created_by_profile_id=model.created_by_profile_id,
            file_name=model.file_name,
            total=model.total,
            created=model.created,
            updated=model.updated,
            skipped=model.skipped,
            columns=model.columns,
            failed_rows=[
                FailedRow(item["row"], item["error"], item["values"]) for item in model.failed_rows
            ],
            warnings=model.warnings,
            created_at=model.created_at,
        )
