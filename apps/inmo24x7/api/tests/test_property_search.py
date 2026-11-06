"""rank: exact room matches first; bigger listings only fill the slots they leave."""

from inmo24x7_api.properties.domain.property import Currency, Operation
from inmo24x7_api.properties.domain.search import Listing, PropertyQuery, rank


def _listing(slug: str, rooms: int, price: int) -> Listing:
    return Listing(
        id=slug,
        title=f"{rooms} ambientes",
        address=f"{slug} 100",
        operation=Operation.RENT,
        zone="Palermo",
        price=price,
        currency=Currency.ARS,
        rooms=rooms,
        link=f"https://example.com/{slug}",
        is_sample=False,
    )


TWO_ROOMS = PropertyQuery(operation=Operation.RENT, zone="Palermo", rooms=2)
# Cheaper than every 2-room listing: price alone would put it first.
BIGGER = _listing("guatemala", 3, 700_000)


def _ids(listings: list[Listing], query: PropertyQuery = TWO_ROOMS) -> list[str]:
    return [match.listing.id for match in rank(listings, query)]


def test_a_bigger_listing_only_fills_the_slot_exact_matches_leave() -> None:
    exact = [_listing("thames", 2, 900_000), _listing("gorriti", 2, 850_000)]

    assert _ids([*exact, BIGGER]) == ["gorriti", "thames", "guatemala"]


def test_a_bigger_listing_is_not_shown_when_exact_matches_fill_the_slots() -> None:
    exact = [
        _listing("gorriti", 2, 850_000),
        _listing("thames", 2, 900_000),
        _listing("soler", 2, 950_000),
    ]

    assert _ids([BIGGER, *exact]) == ["gorriti", "thames", "soler"]


def test_without_exact_matches_bigger_listings_are_shown() -> None:
    bigger = [_listing("guatemala", 3, 1_250_000), _listing("honduras", 4, 1_100_000)]

    assert _ids(bigger) == ["honduras", "guatemala"]


def test_the_budget_still_orders_each_group_and_flags_over_budget() -> None:
    query = PropertyQuery(
        operation=Operation.RENT,
        zone="Palermo",
        rooms=2,
        max_budget=900_000,
        budget_currency=Currency.ARS,
    )
    listings = [
        _listing("soler", 2, 1_000_000),  # over budget, within the tolerance
        _listing("gorriti", 2, 850_000),
        _listing("guatemala", 3, 800_000),
    ]

    matches = rank(listings, query)

    assert [(m.listing.id, m.over_budget) for m in matches] == [
        ("gorriti", False),
        ("soler", True),
        ("guatemala", False),
    ]
