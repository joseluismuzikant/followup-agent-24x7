"""Reads CSV (UTF-8 or Latin-1, comma or semicolon) and XLSX uploads into a `Table`."""

import csv
import io
import zipfile
from datetime import date, datetime

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from ..domain.errors import ImportFileInvalidError
from ..domain.imports import MAX_IMPORT_ROWS, Table

_XLSX_MAGIC = b"PK\x03\x04"


def read_spreadsheet(file_name: str, content: bytes) -> Table:
    if not content.strip():
        raise ImportFileInvalidError("Empty file.")
    if content.startswith(_XLSX_MAGIC) or file_name.lower().endswith(".xlsx"):
        return _read_xlsx(content)
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
        raise ImportFileInvalidError("Binary content in a CSV.")
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    if not rows:
        raise ImportFileInvalidError("No header row.")
    return Table(columns=[cell.strip() for cell in rows[0]], rows=rows[1:])


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _read_xlsx(content: bytes) -> Table:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise ImportFileInvalidError("Not a readable XLSX file.") from error
    try:
        sheet = workbook.worksheets[0]
        rows: list[list[str]] = []
        filled = 0
        for values in sheet.iter_rows(values_only=True):
            row = [_cell(value) for value in values]
            rows.append(row)
            filled += any(cell.strip() for cell in row)
            # Header plus one row over the limit is enough to report the file as too large.
            if filled > MAX_IMPORT_ROWS + 1:
                break
    finally:
        workbook.close()
    if not rows:
        raise ImportFileInvalidError("Empty sheet.")
    return Table(columns=[cell.strip() for cell in rows[0]], rows=rows[1:])
