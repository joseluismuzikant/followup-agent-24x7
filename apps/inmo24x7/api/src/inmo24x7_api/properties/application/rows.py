"""From spreadsheet cells to `PropertyFields`, with the S7 row errors in Spanish.

Headers are matched without accents or case ("Dirección" == "direccion"). Prices accept
Argentine formats: 850.000, 850000, $ 900.000, USD 185.000, 1.250.000,50.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from followup_core.conversation.domain.answers import normalize

from ..domain.errors import ImportFileInvalidError
from ..domain.property import (
    Currency,
    Operation,
    Problem,
    PropertyFields,
    PropertyStatus,
    default_currency,
)

COLUMNS = (
    "titulo",
    "direccion",
    "operacion",
    "zona",
    "precio",
    "moneda",
    "ambientes",
    "link",
    "estado",
)
OPTIONAL_COLUMNS = frozenset({"moneda", "estado"})

MESSAGES: Mapping[Problem, str] = {
    Problem.MISSING_TITLE: "falta el título.",
    Problem.MISSING_ADDRESS: "falta la dirección.",
    Problem.INVALID_OPERATION: "la operación tiene que ser «venta» o «alquiler».",
    Problem.MISSING_ZONE: "falta la zona.",
    Problem.MISSING_PRICE: "falta el precio.",
    Problem.INVALID_PRICE: "el precio no es un número válido.",
    Problem.INVALID_CURRENCY: "la moneda tiene que ser ARS o USD.",
    Problem.MISSING_ROOMS: "faltan los ambientes.",
    Problem.INVALID_ROOMS: "los ambientes tienen que ser un número entre 1 y 20.",
    Problem.MISSING_LINK: "falta el link.",
    Problem.INVALID_LINK: "el link no es una dirección web válida.",
    Problem.INVALID_STATUS: "el estado tiene que ser «publicada» o «pausada».",
    Problem.TOO_LONG: "un texto es demasiado largo.",
}

# The column each problem belongs to, so a row reports the first problem from left to right.
_COLUMN_OF: Mapping[Problem, str] = {
    Problem.MISSING_TITLE: "titulo",
    Problem.MISSING_ADDRESS: "direccion",
    Problem.INVALID_OPERATION: "operacion",
    Problem.MISSING_ZONE: "zona",
    Problem.MISSING_PRICE: "precio",
    Problem.INVALID_PRICE: "precio",
    Problem.INVALID_CURRENCY: "moneda",
    Problem.MISSING_ROOMS: "ambientes",
    Problem.INVALID_ROOMS: "ambientes",
    Problem.MISSING_LINK: "link",
    Problem.INVALID_LINK: "link",
    Problem.INVALID_STATUS: "estado",
    Problem.TOO_LONG: "titulo",
}

_OPERATIONS = {"venta": Operation.SALE, "alquiler": Operation.RENT}
_STATUSES = {"publicada": PropertyStatus.PUBLISHED, "pausada": PropertyStatus.PAUSED}
_USD = re.compile(r"u\$s|us\$|u\$d|usd|dolares?", re.IGNORECASE)
_ARS = re.compile(r"\$|ars|pesos?", re.IGNORECASE)
_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+$")


def row_error(row: int, problem: Problem) -> str:
    return f"Fila {row}: {MESSAGES[problem]}"


@dataclass(frozen=True, slots=True)
class ColumnMap:
    """Position of each known column in the file (unknown columns are ignored)."""

    positions: Mapping[str, int]

    @classmethod
    def of(cls, header: Sequence[str]) -> "ColumnMap":
        positions: dict[str, int] = {}
        for index, name in enumerate(header):
            key = normalize(name).replace(" ", "")
            if key in COLUMNS and key not in positions:
                positions[key] = index
        missing = [
            name for name in COLUMNS if name not in OPTIONAL_COLUMNS and name not in positions
        ]
        if missing:
            raise ImportFileInvalidError(f"Missing columns: {', '.join(missing)}.")
        return cls(positions)

    def cell(self, row: Sequence[str], column: str) -> str:
        index = self.positions.get(column)
        if index is None or index >= len(row):
            return ""
        return row[index].strip()


def parse_amount(text: str) -> int | None:
    """Digits in Argentine notation, without the currency. None when it is not a number."""
    value = text.replace(" ", "")
    if not value:
        return None
    if "," in value:
        whole, _, decimals = value.rpartition(",")
        if not decimals.isdigit() or len(decimals) > 2:
            return None
        value = whole.replace(".", "")
    elif _THOUSANDS.fullmatch(value):
        value = value.replace(".", "")
    elif "." in value:
        # Spreadsheet numbers come as "850000.0".
        whole, _, decimals = value.partition(".")
        if not decimals.isdigit() or len(decimals) > 2:
            return None
        value = whole
    return int(value) if value.isdigit() else None


def parse_price(text: str) -> tuple[int | None, Currency | None]:
    currency: Currency | None = None
    if _USD.search(text):
        currency = Currency.USD
        text = _USD.sub("", text)
    elif _ARS.search(text):
        currency = Currency.ARS
        text = _ARS.sub("", text)
    return parse_amount(text), currency


def parse_row(columns: ColumnMap, row: Sequence[str]) -> PropertyFields | Problem:
    """The fields of one data row, or its first problem from left to right."""
    problems: list[Problem] = []

    operation = _OPERATIONS.get(normalize(columns.cell(row, "operacion")))
    if operation is None:
        problems.append(Problem.INVALID_OPERATION)

    price_text = columns.cell(row, "precio")
    price, price_currency = parse_price(price_text)
    if not price_text:
        problems.append(Problem.MISSING_PRICE)
    elif price is None:
        problems.append(Problem.INVALID_PRICE)

    currency_text = columns.cell(row, "moneda").upper()
    currency: Currency | None = None
    if currency_text:
        currency = Currency(currency_text) if currency_text in Currency.__members__ else None
        if currency is None:
            problems.append(Problem.INVALID_CURRENCY)
    # A currency written in the price ("USD 185.000") wins over the column.
    currency = price_currency or currency

    rooms_text = columns.cell(row, "ambientes")
    rooms = parse_amount(rooms_text)
    if not rooms_text:
        problems.append(Problem.MISSING_ROOMS)
    elif rooms is None:
        problems.append(Problem.INVALID_ROOMS)

    status_text = normalize(columns.cell(row, "estado"))
    status = _STATUSES.get(status_text) if status_text else PropertyStatus.PUBLISHED
    if status is None:
        problems.append(Problem.INVALID_STATUS)

    fields = PropertyFields(
        title=columns.cell(row, "titulo"),
        address=columns.cell(row, "direccion"),
        operation=operation or Operation.SALE,
        zone=columns.cell(row, "zona"),
        price=price or 0,
        currency=currency or default_currency(operation or Operation.SALE),
        rooms=rooms or 0,
        link=columns.cell(row, "link"),
        status=status or PropertyStatus.PUBLISHED,
    ).clean()
    # Field rules apply only where parsing did not already report that column.
    reported = {_COLUMN_OF[problem] for problem in problems}
    problems += [p for p in fields.problems() if _COLUMN_OF[p] not in reported]
    if problems:
        return min(problems, key=lambda problem: COLUMNS.index(_COLUMN_OF[problem]))
    return fields
