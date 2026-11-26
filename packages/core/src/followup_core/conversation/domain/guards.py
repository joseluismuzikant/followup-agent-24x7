"""Deterministic input and output guards for conversation agents, product-agnostic.

The model proposes text and values; these functions only normalise, flag, sanitise and
find things. They never call a model and never decide the flow: the product's graph decides
what to do with what they find.

- `normalize_inbound`: what the agent reads of a visitor's message.
- `suspicion_flags`: codes for text that looks like an attempt to steer the model. Audit
  only: a flagged message is answered like any other, never blocked.
- `sanitize_untrusted`: a value from outside (a visitor, an import, a portal) made safe to
  place inside a prompt's DATA block.
- `find_urls`, `find_contacts`, `find_amounts`: what an outbound text must be checked for.
"""

import re
import unicodedata

# Zero-width and bidi control characters that hide text from a person but not from a model.
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿­]")
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")

# What the prompt's envelope uses; never allowed inside data.
ENVELOPE_OPEN = "<<DATA"
ENVELOPE_CLOSE = "DATA>>"

_OVERRIDE = re.compile(
    r"\b(?:ignor[aáe]\w*|olvid[aáe]\w*|desestim\w*|disregard|forget|override)\b"
    r"[^.\n]{0,40}\b(?:instruc\w*|reglas?|rules?|prompt|indicaciones|todo|everything|"
    r"previous|anteriores?|l[ií]mites?|limits?)\b",
    re.IGNORECASE,
)
_ROLE = re.compile(
    r"(?:^|\n|\s)(?:system|assistant|developer|sistema|asistente)\s*:"
    r"|<\|[^|>]{1,40}\|>|\[/?(?:INST|SYS)\]|</?(?:system|assistant|user|s)>"
    r"|#{2,}\s*(?:system|instrucciones)",
    re.IGNORECASE,
)
_NEW_ROLE = re.compile(
    r"\b(?:ahora sos|ahora eres|you are now|act[uú][aá]\w*\s+como|hac[eé] de cuenta"
    r"|fing[ií]\w*|act as|pretend|from now on|a partir de ahora)\b",
    re.IGNORECASE,
)
_ENVELOPE = re.compile(r"<<|>>|\bDATA>>|<<DATA\b")
_BASE64 = re.compile(r"[A-Za-z0-9+/]{60,}={0,2}")
_LIMITS = re.compile(
    r"\b(?:max_\w+|recursion_limit|token_budget|l[ií]mites?\s+(?:ampliad|aument|desactiv)\w*)",
    re.IGNORECASE,
)
_URL = re.compile(
    r"(?:https?://|www\.)[^\s<>\"'«»]+"
    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|ar|io|ly|me|info|xyz)(?:/[^\s<>\"'«»]*)?\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# A phone: 8 or more digits, with spaces, dashes, dots or parentheses between them.
_PHONE = re.compile(r"(?<![\w/])\+?\(?\d[\d\s().-]{6,}\d(?![\w/])")
_MONEY = re.compile(
    r"(?P<currency>u\$s|us\$|usd|ars|\$)\s*(?P<a>\d[\d.,]*)"
    r"(?:\s*(?P<scale>mil(?:lones?)?|millones?|k)\b)?"
    r"|(?P<b>\d[\d.,]*)\s*(?P<unit>mil(?:lones?)?|millones?|k|pesos|d[oó]lares|usd)\b",
    re.IGNORECASE,
)
_STREET_NUMBER = re.compile(r"\b[A-ZÁÉÍÓÚÑ][\wáéíóúñ.]+\s+(?P<n>\d{2,5})\b")
_INCOME = re.compile(
    r"\b(?:sueldo|salario|ingresos?|cobr[aá]s|gan[aá]s|recibo(?:s)? de sueldo)\b", re.IGNORECASE
)


def normalize_inbound(text: str) -> str:
    """NFKC (fullwidth and compatibility forms become plain letters), no invisible or control
    characters, spaces collapsed inside each line and empty lines dropped. Line breaks stay:
    a burst of messages is read one per line."""
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = "".join(char for char in text if char in "\n\t" or unicodedata.category(char)[0] != "C")
    lines = (_HORIZONTAL_SPACE.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def suspicion_flags(text: str) -> frozenset[str]:
    """Codes only (for the audit log), never the text. Never used to block a message."""
    flags: set[str] = set()
    said = normalize_inbound(text)
    if _OVERRIDE.search(said):
        flags.add("instruction_override")
    if _ROLE.search(said) or _NEW_ROLE.search(said):
        flags.add("role_marker")
    if _ENVELOPE.search(said):
        flags.add("envelope_marker")
    if _BASE64.search(said):
        flags.add("encoded_payload")
    if _LIMITS.search(said):
        flags.add("limit_tampering")
    if find_urls(said):
        flags.add("url")
    return frozenset(flags)


def strip_markers(text: str) -> str:
    """Envelope and role markers removed (`<<`, `>>`, `<|…|>`, `[INST]`, `system:`)."""
    text = _ENVELOPE.sub(" ", text)
    text = re.sub(
        r"<\|[^|>]{0,40}\|>|\[/?(?:INST|SYS)\]|</?(?:system|assistant|user|s)>",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:system|assistant|developer|sistema|asistente)\s*:", " ", text, flags=re.IGNORECASE
    )
    return text


def sanitize_untrusted(value: object, limit: int) -> str:
    """A value from outside, safe inside a prompt's DATA: normalised, on one line, without
    envelope or role markers, at most `limit` characters. Not a filter for meaning: the
    prompt treats DATA as information, and the deterministic checks do the rest."""
    text = normalize_inbound(str(value if value is not None else ""))
    text = " ".join(strip_markers(text).split())
    if len(text) > limit:
        text = text[: max(limit - 1, 0)].rstrip() + "…"
    return text


def find_urls(text: str) -> list[str]:
    """Links, with or without a scheme (an email's domain is not a link)."""
    without_emails = _EMAIL.sub(" ", text)
    return [match.group(0).rstrip(".,;:!?)") for match in _URL.finditer(without_emails)]


def find_contacts(text: str) -> list[str]:
    """Emails and phone numbers (8 or more digits)."""
    found = [match.group(0) for match in _EMAIL.finditer(text)]
    without_emails = _EMAIL.sub(" ", text)
    for match in _PHONE.finditer(without_emails):
        if sum(char.isdigit() for char in match.group(0)) >= 8:
            found.append(match.group(0).strip())
    return found


def _amount(raw: str, unit: str | None) -> int | None:
    digits = raw.strip(".,")
    # "1.200.000", "800,000" and "1,5" (millones): thousands separators vs a decimal part.
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", digits):
        value = float(re.sub(r"[.,]", "", digits))
    else:
        try:
            value = float(digits.replace(",", "."))
        except ValueError:
            return None
    unit = (unit or "").lower()
    if unit.startswith("mill"):
        value *= 1_000_000
    elif unit in ("mil", "k"):
        value *= 1000
    return int(value)


def find_amounts(text: str) -> set[int]:
    """Money amounts ("$ 800.000", "USD 120 mil", "900 mil pesos") and street numbers
    ("Gorriti 4800"), as integers, for comparing a reply with the data it was given."""
    found: set[int] = set()
    for match in _MONEY.finditer(text):
        raw = match.group("a") or match.group("b")
        value = _amount(raw, match.group("unit") or match.group("scale"))
        if value is not None:
            found.add(value)
    for match in _STREET_NUMBER.finditer(text):
        found.add(int(match.group("n")))
    return found


def mentions_income(text: str) -> bool:
    """Talks about the visitor's salary or income next to an amount: never in a reply."""
    return bool(_INCOME.search(text)) and bool(_MONEY.search(text))
