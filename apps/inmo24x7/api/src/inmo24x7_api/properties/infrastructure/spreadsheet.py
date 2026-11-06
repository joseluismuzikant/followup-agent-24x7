"""Property spreadsheets, read with the platform's table reader (followup_platform.tables)."""

from followup_platform.tables import TableFileInvalidError, read_table

from ..domain.errors import ImportFileInvalidError
from ..domain.imports import MAX_IMPORT_ROWS, Table


def read_spreadsheet(file_name: str, content: bytes) -> Table:
    try:
        table = read_table(file_name, content, MAX_IMPORT_ROWS)
    except TableFileInvalidError as error:
        raise ImportFileInvalidError(str(error)) from error
    return Table(columns=table.columns, rows=table.rows)
