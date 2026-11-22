"""A listing page read into a property draft ("Cargar desde un link", roadmap 3c).

The agent pastes the link of their **own** publication (or, when the portal blocks reading
it, the page's text). Nothing here is saved: the draft opens the property form, and the
agent reviews and saves it as usual. The cover image URL is for the preview only (photos
are 3b).

Where each field came from:
- `structured`: the page's schema.org JSON-LD, Open Graph, `<title>` or meta description,
  read by rules (no model);
- `model`: LLM_MODEL read it from the visible text (or the pasted text); the panel marks it
  "Revisá este dato".
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from followup_core.conversation.domain.llm import TokenUsage

from .conditions import PropertyConditions
from .property import Currency, Operation, PropertyStatus

# Requests per agency and hour (page reads and pasted texts; a duplicate link costs none).
LINK_READS_PER_HOUR = 20
MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 10.0
USER_AGENT = "inmo24x7/1.0 (+https://www.inmo24x7.com)"
# Visible text sent to the model: a page's, and a pasted one (longer: it is all listing).
MAX_PAGE_TEXT = 8_000
MAX_PASTED_TEXT = 15_000
MIN_PASTED_TEXT = 80


class FieldSource(StrEnum):
    STRUCTURED = "structured"
    MODEL = "model"


class ReadProblem(StrEnum):
    """Why the page could not be read. The form still opens with the link."""

    BLOCKED = "blocked"  # 401/403/429/451/503: bot protection, as Zonaprop does
    GONE = "gone"  # 404/410: the publication no longer exists
    UNREACHABLE = "unreachable"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    NOT_HTML = "not_html"
    NOT_LISTING = "not_listing"  # read, but nothing in it looks like a property


# Portals by domain, to name them in the messages ("Zonaprop no deja leer la página").
_PORTALS = {
    "zonaprop": "Zonaprop",
    "argenprop": "Argenprop",
    "remax": "RE/MAX",
    "mercadolibre": "Mercado Libre",
    "properati": "Properati",
    "tokkobroker": "Tokko",
    "inmuebles24": "Inmuebles24",
}


def portal_name(url: str) -> str:
    """ "Zonaprop" for www.zonaprop.com.ar; the host without www otherwise."""
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    for key, name in _PORTALS.items():
        if key in host.split("."):
            return name
    return host or "El portal"


def problem_message(problem: ReadProblem, url: str) -> str:
    portal = portal_name(url)
    return {
        ReadProblem.BLOCKED: (
            f"{portal} no deja leer la página. Abrí tu publicación, seleccioná todo (Ctrl+A), "
            "copiá (Ctrl+C) y pegalo acá."
        ),
        ReadProblem.GONE: (
            "La publicación ya no existe en ese link. Completá los datos a mano; el link queda "
            "guardado."
        ),
        ReadProblem.UNREACHABLE: (
            "El portal no nos dejó leer la página. Completá los datos a mano; el link queda "
            "guardado."
        ),
        ReadProblem.TIMEOUT: (
            f"{portal} tardó demasiado en responder. Probá de nuevo o pegá el texto de la "
            "publicación."
        ),
        ReadProblem.TOO_LARGE: (
            "La página es demasiado grande para leerla. Pegá el texto de la publicación."
        ),
        ReadProblem.NOT_HTML: "Ese link no es una página web. Revisá que sea el de la publicación.",
        ReadProblem.NOT_LISTING: (
            "No encontramos los datos de una propiedad en esa página. Revisá que sea el link de "
            "la publicación, o pegá su texto."
        ),
    }[problem]


class ListingUrlError(ValueError):
    """Not an http(s) URL on a standard port, or a host that resolves to a private address."""


class ListingFetchError(Exception):
    def __init__(self, problem: ReadProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


class LinkReadLimitError(Exception):
    """Over LINK_READS_PER_HOUR for the agency."""


class ListingTextError(ValueError):
    """A pasted text too short (or empty) to hold a listing."""


_TRACKING_PREFIXES = ("utm_", "mc_", "pk_")
_TRACKING = frozenset({"fbclid", "gclid", "gbraid", "wbraid", "msclkid", "yclid", "igshid", "si"})


def clean_link(url: str) -> str:
    """The link to store: without tracking parameters (utm_*, fbclid, gclid...) or fragment."""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING and not key.lower().startswith(_TRACKING_PREFIXES)
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), "")
    )


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str  # after redirects
    html: str


class PageFetcher(Protocol):
    def fetch(self, url: str) -> FetchedPage:
        """Raises ListingUrlError (refused before any request) or ListingFetchError."""
        ...


@dataclass(frozen=True, slots=True)
class ModelReading:
    """The model's raw answer (validated by the mapping) and what it cost."""

    values: Mapping[str, Any]
    usage: TokenUsage = TokenUsage()


class ListingModel(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def read(self, text: str) -> ModelReading:
        """Raises LlmUnavailableError on timeout or provider failure."""
        ...


@dataclass(frozen=True, slots=True)
class ListingDraft:
    """What the page said, in our fields. Empty/None = not found (the agent completes it)."""

    link: str
    title: str = ""
    address: str = ""
    operation: Operation | None = None
    zone: str = ""
    price: int | None = None
    currency: Currency | None = None
    rooms: int | None = None
    # Paused when the page says sold, rented or reserved (or no longer exists).
    status: PropertyStatus | None = None
    conditions: PropertyConditions = PropertyConditions()
    image_url: str | None = None
    floor_area_m2: int | None = None
    sources: Mapping[str, FieldSource] = field(default_factory=dict)
    problem: ReadProblem | None = None
    warnings: Sequence[str] = ()
