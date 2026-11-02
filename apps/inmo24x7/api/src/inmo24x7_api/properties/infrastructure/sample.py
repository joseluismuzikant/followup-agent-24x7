"""Sample CABA listings, shown while a tenant has no published property of its own.

Their links are local pages of the panel (`/ejemplo/<slug>`), never invented external URLs.
"""

from ..domain.property import Operation, default_currency
from ..domain.search import Listing


def _sample(
    slug: str,
    title: str,
    address: str,
    operation: str,
    zone: str,
    price: int,
    rooms: int,
) -> Listing:
    kind = Operation(operation)
    return Listing(
        id=slug,
        title=title,
        address=address,
        operation=kind,
        zone=zone,
        price=price,
        currency=default_currency(kind),
        rooms=rooms,
        link=f"/ejemplo/{slug}",
        is_sample=True,
    )


SAMPLE_LISTINGS: tuple[Listing, ...] = (
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
