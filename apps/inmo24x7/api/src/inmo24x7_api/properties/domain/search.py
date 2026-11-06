"""What the agent searches: listings (own or sample) matched against the lead's answers."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from followup_core.conversation.domain.answers import normalize

from .property import Currency, Operation, Property

MAX_RESULTS = 3
# How far over budget a listing may be and still be shown with the over-budget note.
OVER_BUDGET_TOLERANCE = 1.25


@dataclass(frozen=True, slots=True)
class Listing:
    """A property as the agent shows it. `id` is a UUID string for own properties and a slug
    for the sample fixture; `link` is always the real listing link (or a local sample page)."""

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

    @classmethod
    def of(cls, item: Property) -> "Listing":
        fields = item.fields
        return cls(
            id=str(item.id),
            title=fields.title,
            address=fields.address,
            operation=fields.operation,
            zone=fields.zone,
            price=fields.price,
            currency=fields.currency,
            rooms=fields.rooms,
            link=fields.link,
            is_sample=False,
        )


@dataclass(frozen=True, slots=True)
class PropertyQuery:
    operation: Operation | None = None
    zone: str | None = None
    max_budget: int | None = None
    budget_currency: Currency | None = None
    rooms: int | None = None


@dataclass(frozen=True, slots=True)
class PropertyMatch:
    listing: Listing
    over_budget: bool


class PropertySearch(Protocol):
    def search(self, tenant_id: UUID, query: PropertyQuery) -> Sequence[PropertyMatch]: ...


def zone_matches(wanted: str, zone: str) -> bool:
    wanted, zone = normalize(wanted), normalize(zone)
    return wanted in zone or zone in wanted


def rank(listings: Iterable[Listing], query: PropertyQuery) -> list[PropertyMatch]:
    """Operation, zone and rooms filter. Listings with exactly the rooms asked for come first;
    bigger ones only fill the slots they leave. Within each group, with a budget, same
    currency only (no conversion), within budget first, then up to OVER_BUDGET_TOLERANCE over
    it, cheapest first."""
    candidates = [
        item
        for item in listings
        if (query.operation is None or item.operation == query.operation)
        and (query.zone is None or zone_matches(query.zone, item.zone))
        and (query.rooms is None or item.rooms >= query.rooms)
    ]
    if query.rooms is None:
        return _by_budget(candidates, query)[:MAX_RESULTS]
    exact = [item for item in candidates if item.rooms == query.rooms]
    bigger = [item for item in candidates if item.rooms > query.rooms]
    return (_by_budget(exact, query) + _by_budget(bigger, query))[:MAX_RESULTS]


def _by_budget(candidates: Sequence[Listing], query: PropertyQuery) -> list[PropertyMatch]:
    budget = query.max_budget
    if budget is None or query.budget_currency is None:
        ranked = sorted(candidates, key=lambda item: item.price)
        return [PropertyMatch(item, False) for item in ranked]

    comparable = [item for item in candidates if item.currency == query.budget_currency]
    within = sorted((i for i in comparable if i.price <= budget), key=lambda i: i.price)
    over = sorted(
        (i for i in comparable if budget < i.price <= budget * OVER_BUDGET_TOLERANCE),
        key=lambda i: i.price,
    )
    return [PropertyMatch(i, False) for i in within] + [PropertyMatch(i, True) for i in over]
