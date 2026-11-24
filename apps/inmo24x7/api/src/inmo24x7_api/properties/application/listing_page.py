"""From a listing page's HTML (or the model's answer) to our property fields, without network.

Read by rules (`structured`), in this order of trust:
1. schema.org JSON-LD: RealEstateListing / Product / Offer / Residence, Apartment, House...
   (name, offers.price / priceCurrency / availability / businessFunction, address
   (PostalAddress), numberOfRooms, floorSize, petsAllowed, image);
2. Open Graph and product meta (og:title, og:description, og:image, product:price:*);
3. `<title>` and the meta description: the operation ("venta", "alquiler"), the rooms
   ("3 ambientes", "2 amb.", "monoambiente") and conditions it states in words.

Values go through the CSV's parsing (rows.py): prices in Argentine notation, currencies,
guarantees and yes/no flags, so a draft accepts exactly what an import would.
"""

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from followup_core.conversation.domain.answers import normalize

from ..domain.conditions import (
    FIELDS_BY_OPERATION,
    MAX_CONDITIONS_TEXT,
    MAX_CONTRACT_MONTHS,
    PropertyConditions,
)
from ..domain.listing import FieldSource, ListingDraft
from ..domain.property import (
    MAX_ADDRESS_LENGTH,
    MAX_PRICE,
    MAX_ROOMS,
    MAX_TITLE_LENGTH,
    MAX_ZONE_LENGTH,
    Currency,
    Operation,
    PropertyStatus,
)
from .rows import parse_amount, parse_flag, parse_guarantees, parse_price

# The fields that, missing after the rules, make the model read the text.
ESSENTIAL = ("title", "operation", "price", "zone", "rooms")

_SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "head", "iframe"})
_BLOCK_TAGS = frozenset(
    {
        "p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section",
        "article", "header", "footer", "dd", "dt", "td", "th", "ul", "ol", "table", "main",
    }
)  # fmt: skip
_LISTING_TYPES = frozenset(
    {
        "realestatelisting", "product", "offer", "aggregateoffer", "residence", "apartment",
        "house", "singlefamilyresidence", "accommodation", "place", "apartmentcomplex",
        "gatedresidencecommunity", "room", "suite",
    }
)  # fmt: skip


class _PageParser(HTMLParser):
    """JSON-LD blocks, meta tags, the title and the visible text, in one pass."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self.heading = ""
        self._in_heading = False
        self._text: list[str] = []
        self._stack: list[str] = []
        self._skip = 0
        self._in_json_ld = False
        self._in_title = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").strip().lower()
            if key and key not in self.meta and values.get("content"):
                self.meta[key] = values["content"].strip()
            return
        if tag == "script" and "ld+json" in values.get("type", "").lower():
            self._in_json_ld = True
            self._buffer = []
        if tag == "title":
            self._in_title = True
        if tag == "h1" and not self.heading and not self._skip:
            self._in_heading = True
        if tag in _SKIPPED_TAGS:
            self._skip += 1
        if tag in _BLOCK_TAGS:
            self._text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self._in_json_ld = False
        if tag == "title":
            self._in_title = False
        if tag == "h1":
            self._in_heading = False
        if tag in _SKIPPED_TAGS and self._skip:
            self._skip -= 1
        if tag in _BLOCK_TAGS:
            self._text.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip:
            self._text.append(data)
            if self._in_heading:
                self.heading += data

    def text(self) -> str:
        return visible_text("".join(self._text))


def visible_text(text: str) -> str:
    """Lines with their spaces collapsed, without empty lines or repeated ones."""
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line and line not in seen:
            seen.add(line)
            lines.append(line)
    return "\n".join(lines)


@dataclass
class Page:
    url: str
    nodes: list[dict[str, Any]] = field(default_factory=list)
    meta: Mapping[str, str] = field(default_factory=dict)
    title: str = ""
    heading: str = ""  # the first <h1>
    text: str = ""


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    """Every JSON-LD object, through lists, @graph and nested values."""
    if isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            if isinstance(item, dict | list):
                yield from _walk(item)


def read_page(url: str, html: str) -> Page:
    parser = _PageParser()
    parser.feed(html)
    parser.close()
    nodes: list[dict[str, Any]] = []
    for block in parser.json_ld:
        try:
            data = json.loads(block.strip().removeprefix("<!--").removesuffix("-->"))
        except ValueError:
            continue
        nodes.extend(_walk(data))
    return Page(
        url,
        nodes,
        parser.meta,
        title=" ".join(parser.title.split()),
        heading=" ".join(parser.heading.split()),
        text=parser.text(),
    )


def _types(node: Mapping[str, Any]) -> set[str]:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return {str(item).rsplit("/", 1)[-1].lower() for item in kinds if item}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return ""


def _number(value: Any) -> int | None:
    """A JSON number, "85", "85.5" or a QuantitativeValue {"value": 85}."""
    if isinstance(value, dict):
        value = value.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return round(value)
    if isinstance(value, str):
        return parse_amount(value.strip().split(" ")[0])
    return None


def _image(value: Any, base: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    if not isinstance(value, str) or not value.strip():
        return None
    link = urljoin(base, value.strip())
    return link if urlsplit(link).scheme in {"http", "https"} else None


_RENT = re.compile(r"\b(alquiler|alquila|alquilo|renta|arriendo|en alquiler)\b")
_SALE = re.compile(r"\b(venta|vende|vendo|en venta)\b")
_ROOMS = re.compile(r"\b(\d{1,2})\s*(?:amb\b\.?|ambientes?\b)")
_MONO = re.compile(r"\bmonoambiente\b")
_SOLD = re.compile(r"\b(vendid[oa]|alquilad[oa]|reservad[oa]|no disponible)\b")
_SOLD_AVAILABILITY = ("soldout", "outofstock", "discontinued")
_RENT_FUNCTIONS = ("leaseout", "rent")
_SALE_FUNCTIONS = ("sell",)


def operation_in(text: str) -> Operation | None:
    """ "Venta" or "Alquiler" said in words; None when it says neither or both."""
    said = normalize(text)
    rent, sale = bool(_RENT.search(said)), bool(_SALE.search(said))
    if rent == sale:
        return None
    return Operation.RENT if rent else Operation.SALE


_ZONE_IN_TITLE = re.compile(
    r"\ben (?:venta|alquiler)(?: temporario)? en (?P<zone>[a-z][a-z .']{1,40}?)(?=\s*(?:[-,|(]|$))"
)


def zone_in(title: str) -> str:
    """ "Departamento en Venta en Belgrano, Capital Federal" -> "Belgrano" (as written)."""
    said = normalize(title)
    match = _ZONE_IN_TITLE.search(said)
    if match is None or len(said) != len(title):
        return ""
    return " ".join(title[match.start("zone") : match.end("zone")].split())


def rooms_in(text: str) -> int | None:
    said = normalize(text)
    if _MONO.search(said):
        return 1
    match = _ROOMS.search(said)
    if match is None:
        return None
    rooms = int(match.group(1))
    return rooms if 1 <= rooms <= MAX_ROOMS else None


# Conditions stated in words in the title or description (positive or explicitly negative).
_WORD_FLAGS: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    ("apto_credito", re.compile(r"\bapto (?:a )?credito\b"), True),
    ("apto_credito", re.compile(r"\bno apto credito\b"), False),
    ("apto_profesional", re.compile(r"\bapto profesional\b"), True),
    ("amueblado", re.compile(r"\b(?:amoblado|amueblado|amoblada|amueblada)\b"), True),
    ("amueblado", re.compile(r"\bsin muebles\b"), False),
    ("mascotas", re.compile(r"\b(?:acepta|se aceptan|apto) mascotas\b|\bpet friendly\b"), True),
    ("mascotas", re.compile(r"\bno (?:se )?aceptan? mascotas\b|\bsin mascotas\b"), False),
    ("temporal", re.compile(r"\balquiler temporal\b|\btemporario\b"), True),
    ("acepta_permuta", re.compile(r"\bacepta permuta\b"), True),
    ("acepta_financiacion", re.compile(r"\b(?:acepta|con) financiacion\b"), True),
)
_CONTRACT = re.compile(r"\bcontrato (?:minimo )?(?:de )?(\d{1,3}) meses\b")
_GUARANTEE_WORDS = {
    "caucion": re.compile(r"\bseguro de caucion\b|\bcaucion\b"),
    "propietaria": re.compile(r"\bgarantia propietaria\b"),
    "recibo de sueldo": re.compile(r"\brecibos? de sueldo\b"),
}


def conditions_in(text: str) -> dict[str, Any]:
    said = normalize(text)
    found: dict[str, Any] = {}
    for name, pattern, value in _WORD_FLAGS:
        if name not in found and pattern.search(said):
            found[name] = value
    # A negative wins over a positive it contains ("no apto crédito" says "apto crédito").
    for name, pattern, value in _WORD_FLAGS:
        if value is False and pattern.search(said):
            found[name] = False
    months = _CONTRACT.search(said)
    if months and 1 <= int(months.group(1)) <= MAX_CONTRACT_MONTHS:
        found["contrato_minimo_meses"] = int(months.group(1))
    guarantees = [word for word, pattern in _GUARANTEE_WORDS.items() if pattern.search(said)]
    if guarantees:
        found["garantias"] = ", ".join(guarantees)
    return found


@dataclass
class Values:
    """Raw values found, by our field names, before validation."""

    found: dict[str, Any] = field(default_factory=dict)

    def offer(self, name: str, value: Any) -> None:
        if value not in (None, "", []) and name not in self.found:
            self.found[name] = value


def structured_values(page: Page) -> dict[str, Any]:
    """Everything the rules read (JSON-LD first, then Open Graph, then the title and
    description), by our field names, unvalidated."""
    values = Values()
    listings = [node for node in page.nodes if _types(node) & _LISTING_TYPES]
    offers = [node for node in page.nodes if _types(node) & {"offer", "aggregateoffer"}]
    addresses = [node for node in page.nodes if "postaladdress" in _types(node)]

    for node in listings:
        if not _types(node) & {"offer", "aggregateoffer"}:
            values.offer("title", _text(node.get("name")))
    for node in listings:
        values.offer("description", _text(node.get("description")))
        values.offer("rooms", _number(node.get("numberOfRooms")))
        values.offer("floor_area_m2", _number(node.get("floorSize")))
        values.offer("image_url", _image(node.get("image"), page.url))
        pets = node.get("petsAllowed")
        if isinstance(pets, bool):
            values.offer("mascotas", pets)
    for node in offers:
        price = node.get("price", node.get("lowPrice"))
        spec = node.get("priceSpecification")
        if price is None and isinstance(spec, dict):
            price = spec.get("price")
            values.offer("currency", _text(spec.get("priceCurrency")))
        values.offer("price", _text(price))
        values.offer("currency", _text(node.get("priceCurrency")))
        function = _text(node.get("businessFunction")).lower()
        if any(word in function for word in _RENT_FUNCTIONS):
            values.offer("operation", Operation.RENT)
        elif any(word in function for word in _SALE_FUNCTIONS):
            values.offer("operation", Operation.SALE)
        availability = _text(node.get("availability")).lower()
        if any(word in availability for word in _SOLD_AVAILABILITY):
            values.offer("status", PropertyStatus.PAUSED)
    for node in addresses:
        values.offer("address", _text(node.get("streetAddress")))
        values.offer("zone", _text(node.get("addressLocality")) or _text(node.get("addressRegion")))

    meta = page.meta
    values.offer("title", meta.get("og:title", ""))
    values.offer("description", meta.get("og:description", "") or meta.get("description", ""))
    values.offer("image_url", _image(meta.get("og:image"), page.url))
    values.offer("price", meta.get("product:price:amount", "") or meta.get("og:price:amount", ""))
    values.offer(
        "currency",
        meta.get("product:price:currency", "") or meta.get("og:price:currency", ""),
    )
    # The page's heading names the property; <title> often names the site.
    values.offer("title", page.heading)
    values.offer("title", page.title)

    # The title, the description and the URL say the operation and rooms in words.
    words = " ".join(str(values.found.get(name, "")) for name in ("title", "description"))
    values.offer("operation", operation_in(words) or operation_in(urlsplit(page.url).path))
    values.offer("rooms", rooms_in(words))
    for title in (meta.get("og:title", ""), page.heading, page.title):
        values.offer("zone", zone_in(title))
    if _SOLD.search(normalize(str(values.found.get("title", "")))):
        values.offer("status", PropertyStatus.PAUSED)
    for name, value in conditions_in(words).items():
        values.offer(name, value)
    return values.found


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


_OPERATION_WORDS = {
    "venta": Operation.SALE,
    "alquiler": Operation.RENT,
    "sale": Operation.SALE,
    "rent": Operation.RENT,
}
_FLAG_FIELDS = (
    "temporal",
    "amueblado",
    "mascotas",
    "apto_profesional",
    "apto_credito",
    "acepta_financiacion",
    "acepta_permuta",
)


def _operation(value: Any) -> Operation | None:
    if isinstance(value, Operation):
        return value
    said = normalize(str(value or ""))
    return _OPERATION_WORDS.get(said) or (operation_in(said) if said else None)


def _flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    try:
        return parse_flag(str(value or ""))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Mapped:
    """Valid values in our fields; anything that does not parse is left out."""

    fields: dict[str, Any]
    conditions: dict[str, Any]


def map_values(values: Mapping[str, Any]) -> Mapped:
    """The CSV's parsing on raw values (strings, numbers or booleans)."""
    fields: dict[str, Any] = {}
    if title := _clip(values.get("title"), MAX_TITLE_LENGTH):
        fields["title"] = title
    if address := _clip(values.get("address"), MAX_ADDRESS_LENGTH):
        fields["address"] = address
    if zone := _clip(values.get("zone"), MAX_ZONE_LENGTH):
        fields["zone"] = zone
    if operation := _operation(values.get("operation")):
        fields["operation"] = operation

    price_text = values.get("price")
    if isinstance(price_text, int | float) and not isinstance(price_text, bool):
        price_text = str(round(price_text))
    price, said_currency = parse_price(str(price_text or ""))
    if price is not None and 0 < price <= MAX_PRICE:
        fields["price"] = price
    currency_text = str(values.get("currency") or "").strip().upper()
    _, currency_word = parse_price(currency_text) if currency_text else (None, None)
    currency = Currency(currency_text) if currency_text in Currency.__members__ else currency_word
    if currency := said_currency or currency:
        fields["currency"] = currency

    rooms = values.get("rooms")
    rooms = (
        rooms
        if isinstance(rooms, int) and not isinstance(rooms, bool)
        else (parse_amount(str(rooms or "")))
    )
    if rooms is not None and 1 <= rooms <= MAX_ROOMS:
        fields["rooms"] = rooms
    area = values.get("floor_area_m2")
    if isinstance(area, int) and 0 < area < 100_000:
        fields["floor_area_m2"] = area
    if isinstance(values.get("image_url"), str):
        fields["image_url"] = values["image_url"]
    status = values.get("status")
    if status is PropertyStatus.PAUSED or normalize(str(status or "")) in {
        "vendida",
        "alquilada",
        "reservada",
        "paused",
    }:
        fields["status"] = PropertyStatus.PAUSED

    conditions: dict[str, Any] = {}
    for name in _FLAG_FIELDS:
        if (flag := _flag(values.get(name))) is not None:
            conditions[name] = flag
    guarantees = values.get("garantias")
    if isinstance(guarantees, list):
        guarantees = ", ".join(str(item) for item in guarantees)
    try:
        if parsed := parse_guarantees(str(guarantees or "")):
            conditions["garantias"] = parsed
    except ValueError:
        pass
    months = values.get("contrato_minimo_meses")
    months = (
        months
        if isinstance(months, int) and not isinstance(months, bool)
        else (parse_amount(str(months or "")))
    )
    if months is not None and 1 <= months <= MAX_CONTRACT_MONTHS:
        conditions["contrato_minimo_meses"] = months
    if text := _clip(values.get("condiciones"), MAX_CONDITIONS_TEXT):
        conditions["condiciones"] = text
    return Mapped(fields, conditions)


def missing(fields: Mapping[str, Any]) -> list[str]:
    return [name for name in ESSENTIAL if name not in fields]


def build_draft(
    link: str,
    structured: Mapped,
    model: Mapped | None = None,
    warnings: tuple[str, ...] = (),
) -> ListingDraft:
    """Structured values win; the model only fills what they left empty."""
    fields: dict[str, Any] = dict(structured.fields)
    conditions: dict[str, Any] = dict(structured.conditions)
    sources = dict.fromkeys([*fields, *conditions], FieldSource.STRUCTURED)
    if model is not None:
        for name, value in model.fields.items():
            if name not in fields and name not in {"image_url", "floor_area_m2"}:
                fields[name] = value
                sources[name] = FieldSource.MODEL
        for name, value in model.conditions.items():
            if name not in conditions:
                conditions[name] = value
                sources[name] = FieldSource.MODEL
    operation = fields.get("operation")
    if operation is not None:
        allowed = FIELDS_BY_OPERATION[operation]
        conditions = {name: value for name, value in conditions.items() if name in allowed}
    own = PropertyConditions(**conditions)
    sources = {
        name: source
        for name, source in sources.items()
        if name in fields or getattr(own, name, None) is not None
    }
    return ListingDraft(
        link=link,
        title=fields.get("title", ""),
        address=fields.get("address", ""),
        operation=operation,
        zone=fields.get("zone", ""),
        price=fields.get("price"),
        currency=fields.get("currency"),
        rooms=fields.get("rooms"),
        status=fields.get("status"),
        conditions=own,
        image_url=fields.get("image_url"),
        floor_area_m2=fields.get("floor_area_m2"),
        sources={
            name: source
            for name, source in sources.items()
            if name not in {"image_url", "floor_area_m2"}
        },
        warnings=warnings,
    )


def with_link(draft: ListingDraft, link: str) -> ListingDraft:
    return replace(draft, link=link)


# Lines a copied page is full of and a listing never needs ("Iniciar sesión", "Compartir").
_CHROME = re.compile(
    r"^(iniciar sesion|ingresar|registrate|publicar|publica gratis|compartir|favoritos?|"
    r"guardar|denunciar( aviso)?|ver telefono|contactar|enviar( mensaje)?|volver( al listado)?|"
    r"anterior|siguiente|cookies?.*|aceptar|menu|inicio|ayuda|terminos y condiciones.*|"
    r"politica de privacidad.*|descarga la app.*|seguinos.*|\d+ fotos?|ver (mas|todas las) fotos|"
    r"©.*|copyright.*)$"
)


def strip_chrome(text: str) -> str:
    """A pasted page without its menus, buttons and footers, line by line."""
    return "\n".join(
        line for line in visible_text(text).splitlines() if not _CHROME.match(normalize(line))
    )
