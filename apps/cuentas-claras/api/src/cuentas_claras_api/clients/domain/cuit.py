"""CUIT/CUIL: 11 digits whose last one is a check digit (mod 11, AFIP weights).

Stored as the 11 digits; shown as 30-12345678-9.
"""

import re

from .errors import CuitInvalidError

WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
_SEPARATORS = re.compile(r"[\s.\-/]")


def check_digit(first_ten: str) -> int | None:
    """The check digit for the first ten digits; None when none is valid (remainder 1)."""
    remainder = (
        sum(int(digit) * weight for digit, weight in zip(first_ten, WEIGHTS, strict=True)) % 11
    )
    if remainder == 0:
        return 0
    if remainder == 1:
        return None
    return 11 - remainder


def parse_cuit(value: str) -> str:
    """The 11 digits of a CUIT written with or without dashes, dots or spaces."""
    digits = _SEPARATORS.sub("", value)
    if not re.fullmatch(r"\d{11}", digits):
        raise CuitInvalidError(value)
    expected = check_digit(digits[:10])
    if expected is None or expected != int(digits[10]):
        raise CuitInvalidError(value)
    return digits


def format_cuit(digits: str) -> str:
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
