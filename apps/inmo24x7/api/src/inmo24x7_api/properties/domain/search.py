"""What the agent searches: listings (own or sample) matched against the lead's answers."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from followup_core.conversation.domain.answers import normalize

from .conditions import (
    STATUS_ORDER,
    LeadConditions,
    Match,
    MatchStatus,
    PropertyConditions,
    evaluate,
)
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
    # Effective conditions: the property's own, over the agency's defaults.
    conditions: PropertyConditions = PropertyConditions()

    @classmethod
    def of(cls, item: Property, conditions: PropertyConditions | None = None) -> "Listing":
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
            conditions=fields.conditions if conditions is None else conditions,
        )


@dataclass(frozen=True, slots=True)
class PropertyQuery:
    operation: Operation | None = None
    zone: str | None = None
    max_budget: int | None = None
    budget_currency: Currency | None = None
    rooms: int | None = None
    # The lead's situation: never filters, only orders (what fits first).
    lead: LeadConditions | None = None


@dataclass(frozen=True, slots=True)
class PropertyMatch:
    listing: Listing
    over_budget: bool
    # How the lead's situation compares with this listing's conditions.
    match: Match = Match(MatchStatus.SIN_DATOS)


class PropertySearch(Protocol):
    def search(self, tenant_id: UUID, query: PropertyQuery) -> Sequence[PropertyMatch]: ...


def zone_matches(wanted: str, zone: str) -> bool:
    wanted, zone = normalize(wanted), normalize(zone)
    return wanted in zone or zone in wanted


def rank(listings: Iterable[Listing], query: PropertyQuery) -> list[PropertyMatch]:
    """Operation, zone and rooms filter. Listings with exactly the rooms asked for come first;
    bigger ones only fill the slots they leave. Within each group, with a budget, same
    currency only (no conversion), within budget first, then up to OVER_BUDGET_TOLERANCE over
    it, cheapest first. With the lead's situation, what fits goes first, then what has no
    data, then what does not fit; inside a group the listings that meet the lead's wishes
    come first, and otherwise that order stays. Nothing is filtered out by conditions."""
    candidates = [
        item
        for item in listings
        if (query.operation is None or item.operation == query.operation)
        and (query.zone is None or zone_matches(query.zone, item.zone))
        and (query.rooms is None or item.rooms >= query.rooms)
    ]
    if query.rooms is None:
        ordered = _by_budget(candidates, query)
    else:
        exact = [item for item in candidates if item.rooms == query.rooms]
        bigger = [item for item in candidates if item.rooms > query.rooms]
        ordered = _by_budget(exact, query) + _by_budget(bigger, query)
    if query.lead is None:
        return ordered[:MAX_RESULTS]
    lead = query.lead
    evaluated = [
        PropertyMatch(item.listing, item.over_budget, evaluate(lead, item.listing.conditions))
        for item in ordered
    ]
    # sorted() is stable: inside each group the budget / rooms order stays, except that
    # a listing meeting the lead's wishes (apta crédito, acepta mascotas) goes before one
    # that does not.
    return sorted(
        evaluated,
        key=lambda item: (
            STATUS_ORDER[item.match.status],
            bool(item.match.notes),
            -len(item.match.features),
        ),
    )[:MAX_RESULTS]


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
