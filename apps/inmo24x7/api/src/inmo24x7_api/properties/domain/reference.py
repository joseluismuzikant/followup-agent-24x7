"""The property a lead names in their first message, as the website button writes it.

The button ("Consultar por WhatsApp", widget.js) opens WhatsApp with one of two texts:

- on a property page: «Hola, me interesa la propiedad «<título>» (ref. <código>)», where the
  code is what the page declared in `data-propiedad` (our id, Tokko's id or code, or the
  property's link) or else the page's own URL;
- elsewhere: «Hola, les escribo desde su web para hacer una consulta.»

Read here without the model: the text is ours, so a pattern is exact, and a lead who pastes a
listing's link by hand is recognized the same way.
"""

import re
from dataclasses import dataclass
from uuid import UUID

from .operation import Operation
from .property import is_web_link

WEB_GENERIC_TEXT = "Hola, les escribo desde su web para hacer una consulta."
MAX_REFERENCE_LENGTH = 500

_PROPERTY = re.compile(
    r"me interesa la propiedad\s*[«\"“]?(?P<title>[^»\"”]{0,200})[»\"”]?\s*"
    r"\(\s*ref\.?\s*(?P<ref>[^\s)]{1,500})\s*\)",
    re.IGNORECASE,
)
_GENERIC = re.compile(r"les escribo desde su web", re.IGNORECASE)
_LINK = re.compile(r"https?://[^\s<>«»\"']+", re.IGNORECASE)


def web_property_text(title: str, code: str) -> str:
    """The button's text for a property page (widget.js builds the same string)."""
    return f"Hola, me interesa la propiedad «{title}» (ref. {code})"


@dataclass(frozen=True, slots=True)
class PropertyReference:
    property_id: UUID | None = None
    code: str | None = None
    links: tuple[str, ...] = ()
    # The operation the lead already said, to pick between a sale and a rent of the same
    # Tokko property.
    operation: Operation | None = None

    @property
    def is_empty(self) -> bool:
        return self.property_id is None and not self.code and not self.links


@dataclass(frozen=True, slots=True)
class WebReference:
    """What the first message says about where the lead comes from."""

    # Written by the website button (either text).
    from_button: bool
    reference: PropertyReference
    title: str | None = None


def _trim_link(link: str) -> str:
    return link.rstrip(".,;:!?)")


def _reference(value: str) -> PropertyReference:
    value = value.strip()[:MAX_REFERENCE_LENGTH]
    try:
        return PropertyReference(property_id=UUID(value))
    except ValueError:
        pass
    if value.lower().startswith(("http://", "https://")):
        link = _trim_link(value)
        return PropertyReference(links=(link,)) if is_web_link(link) else PropertyReference()
    return PropertyReference(code=value)


def read_web_reference(text: str) -> WebReference | None:
    """None when the message names no property and does not come from the button."""
    match = _PROPERTY.search(text)
    if match is not None:
        title = " ".join(match.group("title").split()) or None
        return WebReference(True, _reference(match.group("ref")), title)
    links = tuple(link for raw in _LINK.findall(text) if is_web_link(link := _trim_link(raw)))[:3]
    from_button = bool(_GENERIC.search(text))
    if not links and not from_button:
        return None
    return WebReference(from_button, PropertyReference(links=links))
