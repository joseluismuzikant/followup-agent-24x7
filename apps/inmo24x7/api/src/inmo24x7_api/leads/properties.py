"""Property search behind a port. Day 3 ships a fixture of sample CABA listings; Day 4 swaps
in the tenant's own properties from the database."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from followup_core.conversation.domain.answers import normalize

Operation = Literal["sale", "rent"]
Currency = Literal["ARS", "USD"]
MAX_RESULTS = 3
# How far over budget a listing may be and still be shown with the over-budget note.
OVER_BUDGET_TOLERANCE = 1.25


@dataclass(frozen=True, slots=True)
class Property:
    id: str
    title: str
    address: str
    operation: Operation
    zone: str
    price: int
    currency: Currency
    rooms: int
    link: str
    is_sample: bool


@dataclass(frozen=True, slots=True)
class PropertyQuery:
    operation: Operation | None = None
    zone: str | None = None
    max_budget: int | None = None
    budget_currency: Currency | None = None
    rooms: int | None = None


@dataclass(frozen=True, slots=True)
class PropertyMatch:
    property: Property
    over_budget: bool


class PropertySearch(Protocol):
    def search(self, query: PropertyQuery) -> Sequence[PropertyMatch]: ...


def _zone_matches(wanted: str, zone: str) -> bool:
    wanted, zone = normalize(wanted), normalize(zone)
    return wanted in zone or zone in wanted


def _sample(
    slug: str,
    title: str,
    address: str,
    operation: Operation,
    zone: str,
    price: int,
    rooms: int,
) -> Property:
    return Property(
        id=slug,
        title=title,
        address=address,
        operation=operation,
        zone=zone,
        price=price,
        currency="USD" if operation == "sale" else "ARS",
        rooms=rooms,
        link=f"/ejemplo/{slug}",
        is_sample=True,
    )


SAMPLE_PROPERTIES: tuple[Property, ...] = (
    _sample(
        "palermo-gorriti-2amb",
        "2 ambientes con balcón",
        "Gorriti 4800, Palermo",
        "sale",
        "Palermo",
        165_000,
        2,
    ),
    _sample(
        "palermo-thames-3amb",
        "3 ambientes luminoso",
        "Thames 1500, Palermo",
        "sale",
        "Palermo",
        245_000,
        3,
    ),
    _sample(
        "palermo-guemes-2amb-alq",
        "2 ambientes amoblado",
        "Güemes 4300, Palermo",
        "rent",
        "Palermo",
        850_000,
        2,
    ),
    _sample(
        "palermo-honduras-mono",
        "Monoambiente a estrenar",
        "Honduras 5600, Palermo",
        "rent",
        "Palermo",
        620_000,
        1,
    ),
    _sample(
        "belgrano-juramento-3amb",
        "3 ambientes con cochera",
        "Juramento 2400, Belgrano",
        "sale",
        "Belgrano",
        198_000,
        3,
    ),
    _sample(
        "belgrano-cabildo-4amb",
        "4 ambientes con dependencia",
        "Av. Cabildo 2100, Belgrano",
        "sale",
        "Belgrano",
        320_000,
        4,
    ),
    _sample(
        "belgrano-mendoza-3amb-alq",
        "3 ambientes con patio",
        "Mendoza 2700, Belgrano",
        "rent",
        "Belgrano",
        1_100_000,
        3,
    ),
    _sample(
        "caballito-acoyte-2amb",
        "2 ambientes reciclado",
        "Acoyte 300, Caballito",
        "sale",
        "Caballito",
        112_000,
        2,
    ),
    _sample(
        "caballito-rivadavia-2amb-alq",
        "2 ambientes frente al parque",
        "Av. Rivadavia 5200, Caballito",
        "rent",
        "Caballito",
        690_000,
        2,
    ),
    _sample(
        "urquiza-triunvirato-3amb",
        "3 ambientes con terraza",
        "Av. Triunvirato 4500, Villa Urquiza",
        "sale",
        "Villa Urquiza",
        175_000,
        3,
    ),
    _sample(
        "urquiza-olazabal-2amb-alq",
        "2 ambientes con amenities",
        "Olazábal 5100, Villa Urquiza",
        "rent",
        "Villa Urquiza",
        720_000,
        2,
    ),
    _sample(
        "nunez-pedraza-2amb",
        "2 ambientes cerca del río",
        "Manuela Pedraza 2300, Núñez",
        "sale",
        "Núñez",
        139_000,
        2,
    ),
    _sample(
        "nunez-libertador-3amb-alq",
        "3 ambientes con vista",
        "Av. del Libertador 7600, Núñez",
        "rent",
        "Núñez",
        980_000,
        3,
    ),
)


class SamplePropertySearch:
    def __init__(self, properties: Sequence[Property] = SAMPLE_PROPERTIES) -> None:
        self._properties = properties

    def search(self, query: PropertyQuery) -> Sequence[PropertyMatch]:
        candidates = [
            item
            for item in self._properties
            if (query.operation is None or item.operation == query.operation)
            and (query.zone is None or _zone_matches(query.zone, item.zone))
            and (query.rooms is None or item.rooms >= query.rooms)
        ]
        budget = query.max_budget
        if budget is None or query.budget_currency is None:
            ranked = sorted(candidates, key=lambda item: item.price)
            return [PropertyMatch(item, False) for item in ranked[:MAX_RESULTS]]

        comparable = [item for item in candidates if item.currency == query.budget_currency]
        within = sorted((i for i in comparable if i.price <= budget), key=lambda i: i.price)
        over = sorted(
            (i for i in comparable if budget < i.price <= budget * OVER_BUDGET_TOLERANCE),
            key=lambda i: i.price,
        )
        matches = [PropertyMatch(i, False) for i in within] + [PropertyMatch(i, True) for i in over]
        return matches[:MAX_RESULTS]
