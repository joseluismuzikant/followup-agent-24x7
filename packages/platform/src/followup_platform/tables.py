"""Reads CSV (UTF-8 or Latin-1, comma or semicolon) and XLSX uploads into a `Table`: header
row and data rows, all as text. Every product's import uses it (properties, invoices)."""

import csv
import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

_XLSX_MAGIC = b"PK\x03\x04"


class TableFileInvalidError(ValueError):
    """Not a CSV or XLSX we can read (the product maps it to its own error)."""


@dataclass(frozen=True, slots=True)
class Table:
    columns: Sequence[str]
    rows: Sequence[Sequence[str]]


def read_table(file_name: str, content: bytes, max_rows: int) -> Table:
    """XLSX reading stops one row past `max_rows`: enough to report the file as too large."""
    if not content.strip():
        raise TableFileInvalidError("Empty file.")
    if content.startswith(_XLSX_MAGIC) or file_name.lower().endswith(".xlsx"):
        return _read_xlsx(content, max_rows)
    return _read_csv(content)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows saves CSV as Latin-1 (cp1252 is a superset that also covers €, “”).
        return content.decode("cp1252", errors="replace")


def _read_csv(content: bytes) -> Table:
    text = _decode(content)
    if "\x00" in text:
        raise TableFileInvalidError("Binary content in a CSV.")
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not rows:
        raise TableFileInvalidError("No header row.")
    return Table(columns=[cell.strip() for cell in rows[0]], rows=rows[1:])


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _read_xlsx(content: bytes, max_rows: int) -> Table:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise TableFileInvalidError("Not a readable XLSX file.") from error
    try:
        sheet = workbook.worksheets[0]
        rows: list[list[str]] = []
        filled = 0
        for values in sheet.iter_rows(values_only=True):
            row = [_cell(value) for value in values]
            rows.append(row)
            filled += any(cell.strip() for cell in row)
            # Header plus one row over the limit is enough to report the file as too large.
            if filled > max_rows + 1:
                break
    finally:
        workbook.close()
    if not rows:
        raise TableFileInvalidError("Empty sheet.")
    return Table(columns=[cell.strip() for cell in rows[0]], rows=rows[1:])
