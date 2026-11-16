"""From spreadsheet cells to `PropertyFields`, with the S7 row errors in Spanish.

Headers are matched without accents or case ("Dirección" == "direccion"). Prices accept
Argentine formats: 850.000, 850000, $ 900.000, USD 185.000, 1.250.000,50.

The conditions columns are optional (files without them import as before):
- yes/no columns accept sí, si, s, yes, x, 1 / no, n, 0 (case and accents ignored); empty
  is "no informado";
- `garantias`: a list separated by commas or slashes, with aliases ("caución", "seguro de
  caución", "garantía propietaria", "recibo de sueldo", ...);
- a column that does not apply to the row's operation (`apto_credito` on a rent) is ignored
  with a warning, never an error.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from followup_core.conversation.domain.answers import normalize

from ..domain.conditions import (
    FIELDS_BY_OPERATION,
    MAX_CONDITIONS_TEXT,
    MAX_CONTRACT_MONTHS,
    ConditionsInvalidError,
    Guarantee,
    PropertyConditions,
)
from ..domain.errors import ImportFileInvalidError
from ..domain.property import (
    Currency,
    Operation,
    Problem,
    PropertyFields,
    PropertyStatus,
    default_currency,
)

# Requirements and features (properties/domain/conditions.py), all optional.
CONDITION_COLUMNS = (
    "garantias",
    "contrato_minimo_meses",
    "temporal",
    "amueblado",
    "mascotas",
    "apto_profesional",
    "apto_credito",
    "acepta_financiacion",
    "acepta_permuta",
    "condiciones",
)
BOOLEAN_COLUMNS = frozenset(CONDITION_COLUMNS) - {
    "garantias",
    "contrato_minimo_meses",
    "condiciones",
}

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
    *CONDITION_COLUMNS,
)
OPTIONAL_COLUMNS = frozenset({"moneda", "estado", *CONDITION_COLUMNS})

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


def row_error(row: int, problem: "Problem | CellError") -> str:
    if isinstance(problem, CellError):
        return f"Fila {row}: {problem.message}"
    return f"Fila {row}: {MESSAGES[problem]}"


@dataclass(frozen=True, slots=True)
class CellError:
    """A condition cell that cannot be read; its message names the column and the value."""

    column: str
    message: str


@dataclass(frozen=True, slots=True)
class ParsedRow:
    fields: PropertyFields
    # Condition columns ignored because they do not apply to the row's operation.
    ignored: tuple[str, ...] = ()


_TRUE = frozenset({"si", "s", "yes", "y", "x", "1", "true", "verdadero"})
_FALSE = frozenset({"no", "n", "0", "false", "falso"})
_GUARANTEE_ALIASES = {
    "propietaria": Guarantee.PROPIETARIA,
    "garantia propietaria": Guarantee.PROPIETARIA,
    "propiedad": Guarantee.PROPIETARIA,
    "caucion": Guarantee.CAUCION,
    "seguro de caucion": Guarantee.CAUCION,
    "seguro caucion": Guarantee.CAUCION,
    "recibo": Guarantee.RECIBO_DE_SUELDO,
    "recibo de sueldo": Guarantee.RECIBO_DE_SUELDO,
    "recibos de sueldo": Guarantee.RECIBO_DE_SUELDO,
    "recibo_de_sueldo": Guarantee.RECIBO_DE_SUELDO,
    "otra": Guarantee.OTRA,
    "otras": Guarantee.OTRA,
}
_OPERATION_WORD = {Operation.RENT: "un alquiler", Operation.SALE: "una venta"}


def _not_understood(column: str, value: str) -> CellError:
    return CellError(column, f"«{column}» tiene un valor que no entiendo: «{value}».")


def parse_flag(text: str) -> bool | None:
    """True, False, or None when the cell is empty. Raises ValueError otherwise."""
    value = normalize(text).strip(" .")
    if not value:
        return None
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(text)


def parse_guarantees(text: str) -> frozenset[Guarantee] | None:
    """ "caución / garantía propietaria" -> {caucion, propietaria}. Raises ValueError with
    the part it did not understand."""
    if not text.strip():
        return None
    found: set[Guarantee] = set()
    for part in re.split(r"[,/;]| y | o ", normalize(text)):
        key = " ".join(part.split())
        if not key:
            continue
        if key not in _GUARANTEE_ALIASES:
            raise ValueError(part.strip())
        found.add(_GUARANTEE_ALIASES[key])
    return frozenset(found) or None


def parse_conditions(
    columns: "ColumnMap", row: Sequence[str], operation: Operation
) -> tuple[PropertyConditions, tuple[str, ...]] | CellError:
    """The row's conditions for its operation and the columns ignored, or the first cell
    error from left to right."""
    allowed = FIELDS_BY_OPERATION[operation]
    values: dict[str, object] = {}
    ignored: list[str] = []
    for column in CONDITION_COLUMNS:
        text = columns.cell(row, column)
        if not text:
            continue
        if column not in allowed:
            ignored.append(column)
            continue
        try:
            if column in BOOLEAN_COLUMNS:
                values[column] = parse_flag(text)
            elif column == "garantias":
                values[column] = parse_guarantees(text)
            elif column == "contrato_minimo_meses":
                months = parse_amount(text)
                if months is None or not 1 <= months <= MAX_CONTRACT_MONTHS:
                    return CellError(
                        column,
                        f"«{column}» tiene que ser un número de meses entre 1 y "
                        f"{MAX_CONTRACT_MONTHS}: «{text}».",
                    )
                values[column] = months
            else:
                if len(" ".join(text.split())) > MAX_CONDITIONS_TEXT:
                    return CellError(
                        column, f"«{column}» es demasiado largo (hasta {MAX_CONDITIONS_TEXT})."
                    )
                values[column] = text
        except ValueError as error:
            shown = str(error) if column == "garantias" else text
            return _not_understood(column, shown)
    try:
        return PropertyConditions(**values), tuple(ignored)  # type: ignore[arg-type]
    except ConditionsInvalidError as error:
        return _not_understood(error.field, columns.cell(row, error.field))


def ignored_warning(row: int, ignored: Sequence[str], operation: Operation) -> str:
    names = ", ".join(f"«{name}»" for name in ignored)
    verb = "no aplica" if len(ignored) == 1 else "no aplican"
    return f"Fila {row}: {names} {verb} a {_OPERATION_WORD[operation]}; lo ignoramos."


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


def parse_row(columns: ColumnMap, row: Sequence[str]) -> ParsedRow | Problem | CellError:
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
    # The conditions come after every other column: their errors are reported last.
    conditions = parse_conditions(columns, row, fields.operation)
    if isinstance(conditions, CellError):
        return conditions
    own, ignored = conditions
    return ParsedRow(replace(fields, conditions=own), ignored)
