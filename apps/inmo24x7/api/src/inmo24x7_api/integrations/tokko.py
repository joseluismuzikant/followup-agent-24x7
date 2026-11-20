"""Tokko Broker: the agency's listings in (`TokkoPropertySource`) and its qualified leads out
as web contacts (`TokkoLeadSink`). The only module that knows Tokko's API.

What Tokko's public docs confirm (developers.tokkobroker.com, "Propiedades" and "Primer
paso"; the resource index at /api/v1/):
- the base URL `.../api/v1/<resource>/?format=json&key=<api_key>&lang=es_ar`, one API key
  per company ("Mi empresa → Permisos → Clave API");
- the resources `property` (listings) and `webcontact` (among others).

What the public docs do not show (the schemas need a key), and is therefore kept here and
listed as "to verify with a real key" in docs/integrations.md:
- the list's pagination (`meta.next`, `meta.total_count`, `objects`) and `limit`/`offset`;
- the property's field names (`id`, `reference_code`, `publication_title`, `address`,
  `fake_address`, `location.name`, `operations[].operation_type`,
  `operations[].prices[].price|currency`, `room_amount`, `suite_amount`, `public_url`);
- that `/property/` lists only active listings (unpublished ones are in `inactiveproperty`);
- the web contact body (`name`, `email`, `cellphone`, `text`, `properties`, `tags`: the
  fields Zapier's "Create Web Contact" action asks for) and that it is a POST.
"""

import logging
from collections.abc import Iterator, Mapping
from typing import Any
from uuid import UUID

import httpx

from ..leads.domain.sinks import LeadSinkError, QualifiedLead, SinkResult
from ..properties.domain.property import (
    MAX_ADDRESS_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_ZONE_LENGTH,
    Currency,
    Operation,
    PropertyFields,
    PropertyOrigin,
    PropertyStatus,
)
from ..properties.domain.sources import ExternalListing, ListingFailure, PropertySourceError

logger = logging.getLogger("inmo24x7.tokko")

# The docs write http://; the same host answers on https, so the key never travels in clear.
DEFAULT_BASE_URL = "https://www.tokkobroker.com/api/v1"
PAGE_SIZE = 50
MAX_LISTINGS = 5000
TIMEOUT_SECONDS = 20.0

KEY_INVALID = "tokko_key_invalid"
UNAVAILABLE = "tokko_unavailable"
BAD_RESPONSE = "tokko_bad_response"
CONTACT_REJECTED = "tokko_contact_rejected"

# Tokko's operation names (es_ar). "Alquiler temporario" is still a rent here; when a
# property has both, the regular rent wins (one listing per operation).
_OPERATIONS: Mapping[str, Operation] = {
    "venta": Operation.SALE,
    "alquiler": Operation.RENT,
    "alquiler temporario": Operation.RENT,
}
_CURRENCIES: Mapping[str, Currency] = {
    "usd": Currency.USD,
    "u$s": Currency.USD,
    "us$": Currency.USD,
    "ars": Currency.ARS,
    "$": Currency.ARS,
}


class TokkoClient:
    """HTTP only; the transport is injectable (tests use a fake Tokko)."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(transport=transport, timeout=timeout)

    def _params(self, key: str, **extra: Any) -> dict[str, Any]:
        return {"key": key, "format": "json", "lang": "es_ar", **extra}

    def get(self, key: str, resource: str, **params: Any) -> Mapping[str, Any]:
        try:
            response = self._http.get(
                f"{self._base_url}/{resource}/", params=self._params(key, **params)
            )
        except httpx.HTTPError as error:
            raise PropertySourceError(UNAVAILABLE) from error
        if response.status_code in (401, 403):
            raise PropertySourceError(KEY_INVALID, retry=False)
        if response.status_code >= 400:
            raise PropertySourceError(UNAVAILABLE, retry=response.status_code >= 500)
        try:
            data = response.json()
        except ValueError as error:
            raise PropertySourceError(BAD_RESPONSE) from error
        if not isinstance(data, dict):
            raise PropertySourceError(BAD_RESPONSE)
        return data

    def check(self, key: str) -> None:
        """ "Probar conexión": one listing read. Raises PropertySourceError."""
        self.get(key, "property", limit=1)

    def post(self, key: str, resource: str, body: Mapping[str, Any]) -> httpx.Response:
        return self._http.post(
            f"{self._base_url}/{resource}/", params=self._params(key), json=dict(body)
        )


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _number(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _zone(item: Mapping[str, Any]) -> str:
    location = item.get("location") or {}
    if not isinstance(location, Mapping):
        return ""
    name = _text(location.get("name"))
    if name:
        return name
    # "Argentina | Capital Federal | Palermo": the last part is the neighborhood.
    full = _text(location.get("short_location") or location.get("full_location"))
    return full.split("|")[-1].strip() if full else ""


def _operations(item: Mapping[str, Any]) -> dict[Operation, Mapping[str, Any]]:
    """One entry per operation of ours; a regular rent wins over a temporary one."""
    found: dict[Operation, tuple[int, Mapping[str, Any]]] = {}
    for operation in item.get("operations") or []:
        if not isinstance(operation, Mapping):
            continue
        name = _text(operation.get("operation_type")).lower()
        ours = _OPERATIONS.get(name)
        if ours is None:
            continue
        rank = 1 if name == "alquiler temporario" else 0
        if ours not in found or rank < found[ours][0]:
            found[ours] = (rank, operation)
    return {key: value for key, (_rank, value) in found.items()}


def _price(operation: Mapping[str, Any]) -> tuple[int, Currency] | str:
    """The first price with an amount, or the reason it cannot be used."""
    prices = [p for p in operation.get("prices") or [] if isinstance(p, Mapping)]
    for price in prices:
        amount = _number(price.get("price"))
        if amount is None:
            continue
        currency = _CURRENCIES.get(_text(price.get("currency")).lower())
        if currency is None:
            return "la moneda no es ARS ni USD."
        return amount, currency
    return "no tiene precio publicado."


def map_property(item: Mapping[str, Any]) -> list[ExternalListing | ListingFailure]:
    """One Tokko property: a listing per operation, or why it cannot be one."""
    external_id = _text(item.get("id"))
    reference = _text(item.get("reference_code")) or None
    address = _text(item.get("fake_address")) or _text(item.get("address"))
    title = _text(item.get("publication_title")) or address or (reference or external_id)

    def failure(reason: str) -> ListingFailure:
        return ListingFailure(external_id, title[:MAX_TITLE_LENGTH], reason)

    if not external_id:
        return [ListingFailure("", title[:MAX_TITLE_LENGTH], "no tiene id de Tokko.")]
    operations = _operations(item)
    if not operations:
        return [failure("no está en venta ni en alquiler.")]
    zone = _zone(item)
    rooms = _number(item.get("room_amount"))
    if rooms is None and (bedrooms := _number(item.get("suite_amount"))):
        rooms = bedrooms + 1  # Tokko counts "ambientes" in room_amount; dormitorios + living
    link = _text(item.get("public_url"))
    problems = [
        (not address, "no tiene dirección."),
        (not zone, "no tiene barrio o localidad."),
        (rooms is None, "no tiene la cantidad de ambientes."),
        (not link, "no tiene link público."),
    ]
    for missing, reason in problems:
        if missing:
            return [failure(reason)]
    assert rooms is not None
    results: list[ExternalListing | ListingFailure] = []
    for operation, data in sorted(operations.items()):
        price = _price(data)
        if isinstance(price, str):
            label = "la venta" if operation is Operation.SALE else "el alquiler"
            results.append(failure(f"{label} {price}"))
            continue
        amount, currency = price
        results.append(
            ExternalListing(
                external_id=external_id,
                external_ref=reference,
                fields=PropertyFields(
                    title=title[:MAX_TITLE_LENGTH],
                    address=address[:MAX_ADDRESS_LENGTH],
                    operation=operation,
                    zone=zone[:MAX_ZONE_LENGTH],
                    price=amount,
                    currency=currency,
                    rooms=min(rooms, 20),
                    link=link,
                    status=PropertyStatus.PUBLISHED,
                ),
            )
        )
    return results


class TokkoPropertySource:
    origin = PropertyOrigin.TOKKO

    def __init__(self, client: TokkoClient, key: str) -> None:
        self._client = client
        self._key = key

    def listings(self) -> Iterator[ExternalListing | ListingFailure]:
        offset = 0
        while offset < MAX_LISTINGS:
            page = self._client.get(self._key, "property", limit=PAGE_SIZE, offset=offset)
            objects = page.get("objects")
            if not isinstance(objects, list):
                raise PropertySourceError(BAD_RESPONSE)
            for item in objects:
                if isinstance(item, Mapping):
                    yield from map_property(item)
            meta = page.get("meta") or {}
            if not objects or not (isinstance(meta, Mapping) and meta.get("next")):
                return
            offset += len(objects)


def contact_body(lead: QualifiedLead) -> dict[str, Any]:
    """A Tokko web contact: who, how to reach them, the properties they chose (Tokko ids
    when the property came from Tokko) and the summary as the contact's text."""
    tokko_ids: list[int | str] = []
    for item in lead.chosen:
        if item.source == PropertyOrigin.TOKKO.value and item.external_id:
            external = item.external_id
            value: int | str = int(external) if external.isdigit() else external
            if value not in tokko_ids:
                tokko_ids.append(value)
    body: dict[str, Any] = {
        "name": lead.name or lead.phone or lead.email or "Consulta de inmo24x7",
        "text": lead.summary,
        "tags": ["inmo24x7"],
    }
    if lead.phone:
        body["cellphone"] = lead.phone
    if lead.email:
        body["email"] = lead.email
    if tokko_ids:
        body["properties"] = tokko_ids
    return body


class TokkoLeadSink:
    def __init__(self, client: TokkoClient, key: str) -> None:
        self._client = client
        self._key = key

    def deliver(self, lead: QualifiedLead, delivery_id: UUID, event: str) -> SinkResult:
        try:
            response = self._client.post(self._key, "webcontact", contact_body(lead))
        except httpx.HTTPError as error:
            raise LeadSinkError(UNAVAILABLE) from error
        status = response.status_code
        if status in (401, 403):
            raise LeadSinkError(KEY_INVALID, status_code=status, retry=False)
        if status == 429 or status >= 500:
            raise LeadSinkError(UNAVAILABLE, status_code=status)
        if status >= 400:
            raise LeadSinkError(CONTACT_REJECTED, status_code=status, retry=False)
        external_id: str | None = None
        try:
            data = response.json()
            if isinstance(data, Mapping) and data.get("id") is not None:
                external_id = str(data["id"])
        except ValueError:
            pass
        return SinkResult(status, external_id)
