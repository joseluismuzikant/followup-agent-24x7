"""Importar facturas: the CSV/XLSX template, row by row. Valid rows are saved even when
others fail; the report says what happened to each, in Spanish."""

import csv
import io
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ...clients.domain.client import Client, ClientFields
from ...clients.domain.repository import ClientRepository
from ..domain.errors import ImportFileInvalidError, ImportNotFoundError, ImportTooLargeError
from ..domain.imports import (
    COLUMNS,
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    REQUIRED_COLUMNS,
    FailedRow,
    InvoiceImport,
    InvoiceImportRepository,
)
from ..domain.invoice import Invoice, InvoiceFields, InvoiceStatus
from ..domain.repository import InvoiceRepository
from ..domain.status import today_in
from .rows import InvoiceRow, RowError, read_row

Clock = Callable[[], datetime]
TimezoneOf = Callable[[UUID], str]
# The table reader (followup_platform.tables, adapted by the container): columns and rows.
ReadTable = Callable[[str, bytes], tuple[Sequence[str], Sequence[Sequence[str]]]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _merged(existing: Client, row: ClientFields) -> ClientFields:
    """A row fills in or corrects a client's data; an empty cell keeps what is there."""

    def pick(new: str, old: str | None) -> str:
        return new.strip() or (old or "")

    return ClientFields(
        name=row.name,
        subtitle=pick(row.subtitle, existing.subtitle),
        cuit=pick(row.cuit, existing.cuit),
        contact_name=pick(row.contact_name, existing.contact_name),
        whatsapp=pick(row.whatsapp, existing.whatsapp),
        email=pick(row.email, existing.email),
        notes=existing.notes or "",
    )


class ImportInvoices:
    def __init__(
        self,
        clients: ClientRepository,
        invoices: InvoiceRepository,
        imports: InvoiceImportRepository,
        read_table: ReadTable,
        audit: AuditLog,
        timezone_of: TimezoneOf,
        clock: Clock = utc_now,
    ) -> None:
        self._clients = clients
        self._invoices = invoices
        self._imports = imports
        self._read_table = read_table
        self._audit = audit
        self._timezone_of = timezone_of
        self._clock = clock

    def execute(
        self, tenant_id: UUID, profile_id: UUID | None, file_name: str, content: bytes
    ) -> InvoiceImport:
        if len(content) > MAX_IMPORT_BYTES:
            raise ImportTooLargeError(file_name)
        columns, rows = self._read_table(file_name, content)
        names = [column.strip().lower() for column in columns]
        if not set(REQUIRED_COLUMNS) <= set(names):
            raise ImportFileInvalidError("Missing template columns.")
        numbered = [
            (index, list(row))
            for index, row in enumerate(rows, start=2)
            if any(cell.strip() for cell in row)
        ]
        if len(numbered) > MAX_IMPORT_ROWS:
            raise ImportTooLargeError(file_name)

        now = self._clock()
        today = today_in(self._timezone_of(tenant_id), now)
        created = updated = skipped = 0
        failed: list[FailedRow] = []
        warnings: list[str] = []
        for row_number, cells in numbered:
            original = {
                column: cells[i] if i < len(cells) else "" for i, column in enumerate(columns)
            }
            values = {name: cells[i] if i < len(cells) else "" for i, name in enumerate(names)}
            try:
                row = read_row(values, today)
            except RowError as error:
                failed.append(
                    FailedRow(row_number, f"Fila {row_number}: {error.message}", original)
                )
                continue
            outcome = self._save(tenant_id, row, now)
            if outcome == "created":
                created += 1
            elif outcome == "updated":
                updated += 1
            else:
                skipped += 1
                if outcome:
                    warnings.append(f"Fila {row_number}: {outcome}")

        record = InvoiceImport(
            id=uuid4(),
            tenant_id=tenant_id,
            created_by_profile_id=profile_id,
            file_name=file_name[:255],
            total=len(numbered),
            created=created,
            updated=updated,
            skipped=skipped,
            columns=list(columns),
            failed_rows=failed,
            warnings=warnings,
            created_at=now,
        )
        self._imports.add(record)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER if profile_id else ActorKind.SYSTEM,
                CuentasAction.INVOICES_IMPORTED,
                {
                    "created": created,
                    "updated": updated,
                    "skipped": skipped,
                    "failed": len(failed),
                    "import_id": str(record.id),
                },
                actor_profile_id=profile_id,
            )
        )
        return record

    def _client(self, tenant_id: UUID, fields: ClientFields, now: datetime) -> Client:
        """By CUIT when the row has one, else by name (accents, case and spaces folded)."""
        probe = Client.create(tenant_id, fields, now)
        existing = None
        if probe.cuit:
            existing = self._clients.find_by_cuit(tenant_id, probe.cuit)
        if existing is None:
            existing = self._clients.find_by_name_key(tenant_id, probe.name_key)
            if (
                existing is not None
                and existing.cuit
                and probe.cuit
                and existing.cuit != probe.cuit
            ):
                existing = None  # the same name with another CUIT is another company
        if existing is None:
            self._clients.add(probe)
            return probe
        updated = existing.with_changes(_merged(existing, fields), now)
        if updated != replace(existing, updated_at=now):
            self._clients.save(updated)
        return updated

    def _save(self, tenant_id: UUID, row: InvoiceRow, now: datetime) -> str:
        """ "created", "updated", or why the row was left alone ("" when there is nothing to
        warn about)."""
        current = self._invoices.find_by_number(
            tenant_id, row.invoice_type, row.point_of_sale, row.number
        )
        if current is not None and current.status is InvoiceStatus.PAID:
            return "" if row.paid else "la factura ya figuraba pagada; no la cambiamos."
        if current is not None and current.status is InvoiceStatus.CANCELLED:
            return "la factura estaba anulada; no la cambiamos."
        client = self._client(tenant_id, row.client, now)
        fields = InvoiceFields(
            client_id=client.id,
            invoice_type=row.invoice_type,
            point_of_sale=row.point_of_sale,
            number=row.number,
            issue_date=row.issue_date,
            due_date=row.due_date,
            amount=row.amount,
            currency=row.currency,
            description=row.description,
        )
        invoice = (
            Invoice.create(tenant_id, fields, now)
            if current is None
            else current.with_changes(fields, now)
        )
        if row.paid and row.paid_at is not None and row.paid_via is not None:
            invoice = invoice.mark_paid(row.paid_at, row.paid_via, None, now)
        if current is None:
            self._invoices.add(invoice)
            return "created"
        self._invoices.save(invoice)
        return "updated"


def _csv(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    buffer = io.StringIO()
    # Excel in es-AR expects ";" and needs the BOM to read UTF-8.
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return "﻿" + buffer.getvalue()


class GetImportErrors:
    """The failed rows of an import, as a CSV with an "error" column first."""

    def __init__(self, imports: InvoiceImportRepository) -> None:
        self._imports = imports

    def execute(self, tenant_id: UUID, import_id: UUID) -> str:
        record = self._imports.get(tenant_id, import_id)
        if record is None:
            raise ImportNotFoundError(str(import_id))
        header = ["error", *record.columns]
        rows = [
            [failed.error, *(failed.values.get(column, "") for column in record.columns)]
            for failed in record.failed_rows
        ]
        return _csv(header, rows)


def import_template() -> str:
    example = (
        "Edificio Güemes 2140",
        "Administración Pérez",
        "30-71234567-1",
        "Marta Pérez",
        "11 5555-0101",
        "administracion@ejemplo.com",
        "B",
        "3",
        "1245",
        "01/11/2026",
        "10/11/2026",
        "180.000,50",
        "ARS",
        "Mantenimiento mensual noviembre",
        "pendiente",
        "",
        "",
    )
    return _csv(COLUMNS, [example])
