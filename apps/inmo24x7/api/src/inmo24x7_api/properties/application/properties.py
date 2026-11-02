import csv
import io
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from followup_core.conversation.application.threads import Clock, utc_now

from ..domain.errors import (
    ImportNotFoundError,
    ImportTooLargeError,
    PropertyInvalidError,
    PropertyLinkTakenError,
    PropertyNotFoundError,
)
from ..domain.imports import (
    MAX_IMPORT_BYTES,
    MAX_IMPORT_ROWS,
    FailedRow,
    PropertyImport,
    Table,
)
from ..domain.property import Property, PropertyChanges, PropertyFields, PropertyStatus
from ..domain.repositories import (
    PropertyFilters,
    PropertyImportRepository,
    PropertyPage,
    PropertyRepository,
)
from .rows import COLUMNS, ColumnMap, parse_row, row_error

PAGE_SIZE = 20

SpreadsheetReader = Callable[[str, bytes], Table]
"""Reads a CSV or XLSX upload. Raises ImportFileInvalidError when it cannot."""


def _valid(fields: PropertyFields) -> PropertyFields:
    fields = fields.clean()
    problems = fields.problems()
    if problems:
        raise PropertyInvalidError(problems)
    return fields


class CreateProperty:
    def __init__(self, properties: PropertyRepository, clock: Clock = utc_now) -> None:
        self._properties = properties
        self._clock = clock

    def execute(self, tenant_id: UUID, fields: PropertyFields) -> Property:
        fields = _valid(fields)
        if self._properties.get_by_link(tenant_id, fields.link) is not None:
            raise PropertyLinkTakenError(fields.link)
        now = self._clock()
        item = Property(uuid4(), tenant_id, fields, now, now)
        self._properties.add(item)
        return item


class UpdateProperty:
    def __init__(self, properties: PropertyRepository, clock: Clock = utc_now) -> None:
        self._properties = properties
        self._clock = clock

    def execute(self, tenant_id: UUID, property_id: UUID, changes: PropertyChanges) -> Property:
        current = self._properties.get(tenant_id, property_id)
        if current is None:
            raise PropertyNotFoundError(str(property_id))
        fields = _valid(changes.apply(current.fields))
        other = self._properties.get_by_link(tenant_id, fields.link)
        if other is not None and other.id != property_id:
            raise PropertyLinkTakenError(fields.link)
        if fields == current.fields:
            return current
        updated = current.with_fields(fields, self._clock())
        self._properties.update(updated)
        return updated


class SetPropertyStatus:
    """Publish or pause. There is no delete: pausing hides a property from the agent."""

    def __init__(self, properties: PropertyRepository, clock: Clock = utc_now) -> None:
        self._properties = properties
        self._clock = clock

    def execute(self, tenant_id: UUID, property_id: UUID, status: PropertyStatus) -> Property:
        current = self._properties.get(tenant_id, property_id)
        if current is None:
            raise PropertyNotFoundError(str(property_id))
        if current.fields.status is status:
            return current
        updated = current.with_fields(replace(current.fields, status=status), self._clock())
        self._properties.update(updated)
        return updated


class ListProperties:
    def __init__(self, properties: PropertyRepository) -> None:
        self._properties = properties

    def execute(self, tenant_id: UUID, filters: PropertyFilters, page: int = 1) -> PropertyPage:
        return self._properties.list(tenant_id, filters, max(page, 1), PAGE_SIZE)


class ImportProperties:
    """Each row is validated on its own: valid rows are saved even when others fail.

    A row whose link already exists for the tenant updates that property (also when the link
    repeats inside the same file: the last row wins). Rows that did not change are not
    written, so importing the same file twice changes nothing.
    """

    def __init__(
        self,
        properties: PropertyRepository,
        imports: PropertyImportRepository,
        reader: SpreadsheetReader,
        clock: Clock = utc_now,
    ) -> None:
        self._properties = properties
        self._imports = imports
        self._reader = reader
        self._clock = clock

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID | None,
        file_name: str,
        content: bytes,
    ) -> PropertyImport:
        if len(content) > MAX_IMPORT_BYTES:
            raise ImportTooLargeError(f"{len(content)} bytes.")
        table = self._reader(file_name, content)
        columns = ColumnMap.of(table.columns)
        rows = _numbered(table)
        if len(rows) > MAX_IMPORT_ROWS:
            raise ImportTooLargeError(f"{len(rows)} rows.")

        now = self._clock()
        created = updated = 0
        failed: list[FailedRow] = []
        for number, row in rows:
            parsed = parse_row(columns, row)
            if not isinstance(parsed, PropertyFields):
                failed.append(
                    FailedRow(number, row_error(number, parsed), _values(table.columns, row))
                )
                continue
            if self._upsert(tenant_id, parsed, now):
                created += 1
            else:
                updated += 1

        record = PropertyImport(
            id=uuid4(),
            tenant_id=tenant_id,
            created_by_profile_id=profile_id,
            file_name=file_name[:200],
            total=created + updated + len(failed),
            created=created,
            updated=updated,
            columns=list(table.columns),
            failed_rows=failed,
            created_at=now,
        )
        self._imports.add(record)
        return record

    def _upsert(self, tenant_id: UUID, fields: PropertyFields, now: datetime) -> bool:
        """True when the property is new."""
        current = self._properties.get_by_link(tenant_id, fields.link)
        if current is None:
            self._properties.add(Property(uuid4(), tenant_id, fields, now, now))
            return True
        if current.fields != fields:
            self._properties.update(current.with_fields(fields, now))
        return False


def _numbered(table: Table) -> list[tuple[int, list[str]]]:
    """Data rows with their spreadsheet number (header = 1), skipping blank lines."""
    return [
        (index + 2, list(row))
        for index, row in enumerate(table.rows)
        if any(cell.strip() for cell in row)
    ]


def _values(columns: Sequence[str], row: list[str]) -> dict[str, str]:
    return {name: row[index] if index < len(row) else "" for index, name in enumerate(columns)}


def _csv(header: list[str], rows: list[list[str]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    # The BOM makes Excel open accents correctly.
    return "﻿" + buffer.getvalue()


class GetImportErrors:
    """The failed rows as a CSV: the original columns plus an "error" column."""

    def __init__(self, imports: PropertyImportRepository) -> None:
        self._imports = imports

    def execute(self, tenant_id: UUID, import_id: UUID) -> str:
        record = self._imports.get(tenant_id, import_id)
        if record is None:
            raise ImportNotFoundError(str(import_id))
        columns = list(record.columns)
        return _csv(
            [*columns, "error"],
            [
                [*(item.values.get(name, "") for name in columns), item.error]
                for item in record.failed_rows
            ],
        )


TEMPLATE_EXAMPLE = [
    "2 ambientes luminoso",
    "Gorriti 4800",
    "alquiler",
    "Palermo",
    "850.000",
    "ARS",
    "2",
    "https://www.tuinmobiliaria.com.ar/propiedades/gorriti-4800",
    "publicada",
]


def import_template() -> str:
    return _csv(list(COLUMNS), [TEMPLATE_EXAMPLE])
