"""Invoice numbers the way ARCA prints them: "B 0003-00001245" (type, point of sale padded to
4 digits, or 5 above 9999, and the number padded to 8)."""

import re
from dataclasses import dataclass
from enum import StrEnum


class InvoiceType(StrEnum):
    A = "A"
    B = "B"
    C = "C"


MAX_POINT_OF_SALE = 99_999
MAX_NUMBER = 99_999_999

# "B 0003-00001245", "B 3-1245", "0003-00001245", "3-1245", "b0003 00001245", "1245".
_QUERY = re.compile(
    r"^\s*(?:(?P<type>[abcABC])\s*)?(?:(?P<pos>\d{1,5})\s*[-\s]\s*)?(?P<number>\d{1,8})\s*$"
)


def format_point_of_sale(point_of_sale: int) -> str:
    return f"{point_of_sale:05d}" if point_of_sale > 9999 else f"{point_of_sale:04d}"


def format_number(invoice_type: InvoiceType, point_of_sale: int, number: int) -> str:
    return f"{invoice_type.value} {format_point_of_sale(point_of_sale)}-{number:08d}"


@dataclass(frozen=True, slots=True)
class NumberQuery:
    """An invoice number typed in the search box, in any of the usual formats."""

    number: int
    point_of_sale: int | None = None
    invoice_type: InvoiceType | None = None


def parse_number_query(text: str) -> NumberQuery | None:
    match = _QUERY.fullmatch(text)
    if match is None:
        return None
    number = int(match.group("number"))
    pos = match.group("pos")
    kind = match.group("type")
    if number == 0:
        return None
    return NumberQuery(
        number=number,
        point_of_sale=int(pos) if pos else None,
        invoice_type=InvoiceType(kind.upper()) if kind else None,
    )
