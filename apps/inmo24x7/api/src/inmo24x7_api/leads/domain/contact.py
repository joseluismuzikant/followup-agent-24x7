"""Contact details a lead leaves: an email, or a phone number stored as E.164 and shown as
"+54 9 11 5555-0188" (the same rules as WhatsApp numbers)."""

import re

from followup_core.messaging.domain.phones import display, to_e164

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")
_PHONE_CHARS = re.compile(r"^[\d\s()+.\-]+$")


def normalize_phone(text: str) -> str | None:
    if not _PHONE_CHARS.fullmatch(text.strip()):
        return None
    e164 = to_e164(text)
    return display(e164) if e164 else None


def normalize_contact(text: str) -> str | None:
    """A lowercased email or a normalized phone; None when it is neither."""
    value = text.strip()
    if "@" in value:
        email = value.lower()
        return email if _EMAIL.fullmatch(email) and len(email) <= 120 else None
    return normalize_phone(value)
