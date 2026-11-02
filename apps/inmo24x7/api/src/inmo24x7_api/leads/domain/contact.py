"""Contact details a lead leaves: an email, or an Argentine phone number as +54 9 ...."""

import re

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
_PHONE_CHARS = re.compile(r"^[\d\s()+.\-]+$")


def _national(digits: str) -> str | None:
    """The 10-digit national number (area code + subscriber), without 0, 15, 54 or 9."""
    if digits.startswith("54"):
        digits = digits[2:]
        if digits.startswith("9"):
            digits = digits[1:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 12:
        # Area code (2 to 4 digits) followed by the mobile prefix 15.
        for area in (2, 3, 4):
            if digits[area : area + 2] == "15":
                digits = digits[:area] + digits[area + 2 :]
                break
    if len(digits) == 10 and digits.startswith("15"):
        # "15 5555-1234" without area code: Buenos Aires.
        digits = "11" + digits[2:]
    if len(digits) == 10 and digits[0] in "123" and not digits.startswith("10"):
        return digits
    return None


def normalize_phone(text: str) -> str | None:
    if not _PHONE_CHARS.fullmatch(text.strip()):
        return None
    national = _national(re.sub(r"\D", "", text))
    if national is None:
        return None
    if national.startswith("11"):
        return f"+54 9 11 {national[2:6]}-{national[6:]}"
    return f"+54 9 {national}"


def normalize_contact(text: str) -> str | None:
    """A lowercased email or a normalized phone; None when it is neither."""
    value = text.strip()
    if "@" in value:
        email = value.lower()
        return email if _EMAIL.fullmatch(email) and len(email) <= 120 else None
    return normalize_phone(value)
