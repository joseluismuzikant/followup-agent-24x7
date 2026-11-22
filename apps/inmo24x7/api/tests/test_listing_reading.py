"""Reading a listing page without network: the structured data of Zonaprop-, Argenprop- and
RE/MAX-like pages (written for the tests), the CSV's parsing on the values, and the SSRF
guard of the fetcher (mocked HTTP and DNS)."""

from pathlib import Path

import httpx
import pytest
from inmo24x7_api.properties.application.listing_page import (
    build_draft,
    map_values,
    read_page,
    strip_chrome,
    structured_values,
)
from inmo24x7_api.properties.domain.conditions import Guarantee
from inmo24x7_api.properties.domain.listing import (
    USER_AGENT,
    FieldSource,
    ListingFetchError,
    ListingUrlError,
    ReadProblem,
    clean_link,
    portal_name,
    problem_message,
)
from inmo24x7_api.properties.domain.property import Currency, Operation, PropertyStatus
from inmo24x7_api.properties.infrastructure.listing_model import FakeListingModel
from inmo24x7_api.properties.infrastructure.page_fetcher import SafePageFetcher, is_public_address

FIXTURES = Path(__file__).parent / "fixtures" / "listings"
PUBLIC = "93.184.216.34"


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text("utf-8")


def draft_of(name: str, url: str = "https://www.portal.example/p/1"):
    page = read_page(url, fixture(name))
    return build_draft(url, map_values(structured_values(page)))


def test_a_zonaprop_like_page_fills_everything_from_its_json_ld() -> None:
    draft = draft_of("zonaprop_like")

    assert (draft.title, draft.address, draft.zone) == (
        "2 ambientes luminoso con balcón",
        "Gorriti 4800",
        "Palermo",
    )
    assert (draft.operation, draft.price, draft.currency, draft.rooms) == (
        Operation.RENT,
        850_000,
        Currency.ARS,
        2,
    )
    assert draft.floor_area_m2 == 48
    assert draft.image_url == "https://img.portal.example/gorriti-4800/1.jpg"
    # Conditions the page states: guarantees, minimum contract and pets.
    assert draft.conditions.garantias == {Guarantee.CAUCION, Guarantee.PROPIETARIA}
    assert draft.conditions.contrato_minimo_meses == 24
    assert draft.conditions.mascotas is True
    assert set(draft.sources.values()) == {FieldSource.STRUCTURED}


def test_an_argenprop_like_page_with_only_open_graph() -> None:
    draft = draft_of("argenprop_like")

    assert draft.title == "Departamento en Venta en Belgrano - 3 ambientes con balcón"
    assert (draft.operation, draft.price, draft.currency) == (Operation.SALE, 185_000, Currency.USD)
    assert (draft.rooms, draft.zone) == (3, "Belgrano")  # both said in the title
    assert draft.address == ""  # "Cabildo al 2100" is left to the model or the agent
    assert draft.image_url == "https://img.portal.example/cabildo-2100/portada.jpg"
    assert draft.conditions.apto_credito is True and draft.conditions.apto_profesional is True


def test_a_remax_like_page_with_a_graph_and_a_price_specification() -> None:
    draft = draft_of("remax_like")

    assert (draft.title, draft.address, draft.zone) == (
        "Casa 4 ambientes con jardín y pileta",
        "Los Robles 350",
        "Pilar",
    )
    assert (draft.operation, draft.price, draft.currency, draft.rooms) == (
        Operation.SALE,
        320_000,
        Currency.USD,
        4,
    )
    assert draft.floor_area_m2 == 180
    assert draft.image_url == "https://img.portal.example/pilar/casa.jpg"


def test_a_page_with_only_text_leaves_the_rest_to_the_model() -> None:
    page = read_page("https://www.inmo.example/ph", fixture("text_only"))
    structured = map_values(structured_values(page))
    # Scripts and styles are never part of the text the model reads.
    assert "no debe leerse" not in page.text
    # Only the heading is structured; the body's text is the model's to read.
    assert structured.fields == {"title": "Hermoso PH reciclado"}

    reading = FakeListingModel().read(page.text)
    draft = build_draft("https://www.inmo.example/ph", structured, map_values(reading.values))

    assert draft.title == "Hermoso PH reciclado"
    assert draft.sources["title"] is FieldSource.STRUCTURED
    assert (draft.price, draft.currency, draft.address) == (1_100_000, Currency.ARS, "Thames 600")
    assert (draft.operation, draft.rooms, draft.zone) == (Operation.RENT, 3, "")
    assert draft.sources["price"] is FieldSource.MODEL
    assert draft.conditions.mascotas is False


def test_model_values_go_through_the_csv_parsing() -> None:
    model = map_values(
        {
            "title": "  3 amb.  con   cochera ",
            "operation": "Venta",
            "price": "U$S 120.000",
            "rooms": "3",
            "garantias": ["caución", "inventada"],  # one it does not know: none are taken
            "apto_credito": "sí",
            "mascotas": "tal vez",
            "contrato_minimo_meses": 500,
        }
    )

    assert model.fields == {
        "title": "3 amb. con cochera",
        "operation": Operation.SALE,
        "price": 120_000,
        "currency": Currency.USD,
        "rooms": 3,
    }
    assert model.conditions == {"apto_credito": True}


def test_conditions_that_do_not_apply_to_the_operation_are_dropped() -> None:
    draft = build_draft(
        "https://x.example/a",
        map_values({"operation": "alquiler", "apto_credito": True, "amueblado": True}),
    )

    assert draft.conditions.amueblado is True and draft.conditions.apto_credito is None
    assert "apto_credito" not in draft.sources


def test_a_sold_listing_is_read_as_paused() -> None:
    html = fixture("remax_like").replace('"businessFunction"', '"availability": "SoldOut", "x"')
    page = read_page("https://www.portal.example/p/1", html)

    assert map_values(structured_values(page)).fields["status"] is PropertyStatus.PAUSED


def test_the_stored_link_has_no_tracking_parameters() -> None:
    assert (
        clean_link("https://WWW.Zonaprop.com.ar/p/123.html?utm_source=wa&fbclid=x&id=7#fotos")
        == "https://www.zonaprop.com.ar/p/123.html?id=7"
    )


def test_portals_are_named_from_the_domain() -> None:
    assert portal_name("https://www.zonaprop.com.ar/propiedades/x") == "Zonaprop"
    assert portal_name("https://www.argenprop.com/x") == "Argenprop"
    assert portal_name("https://www.remax.com.ar/listings/x") == "RE/MAX"
    assert portal_name("https://www.tuinmobiliaria.com.ar/p/1") == "tuinmobiliaria.com.ar"
    assert problem_message(ReadProblem.BLOCKED, "https://www.zonaprop.com.ar/p").startswith(
        "Zonaprop no deja leer la página. Abrí tu publicación, seleccioná todo (Ctrl+A), "
        "copiá (Ctrl+C) y pegalo acá."
    )
    assert problem_message(ReadProblem.UNREACHABLE, "https://x.example/p") == (
        "El portal no nos dejó leer la página. Completá los datos a mano; el link queda guardado."
    )


def test_a_pasted_page_loses_its_menus_and_buttons() -> None:
    pasted = "Iniciar sesión\nPublicar\n  Departamento   en venta \nCompartir\n12 fotos\nUSD 99.000"

    assert strip_chrome(pasted) == "Departamento en venta\nUSD 99.000"


# The fetcher.


class Site:
    """A mocked web: responses by (host, path), and every request it saw."""

    def __init__(self, routes: dict[tuple[str, str], httpx.Response]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.headers["host"], request.url.path)
        return self.routes.get(key, httpx.Response(404))


def resolver(addresses: dict[str, list[str]]):
    def resolve(host: str, port: int) -> list[str]:
        return addresses.get(host, [PUBLIC])

    return resolve


def html(body: str, **headers: str) -> httpx.Response:
    return httpx.Response(
        200, content=body.encode(), headers={"content-type": "text/html; charset=utf-8", **headers}
    )


def fetcher(site: Site, addresses: dict[str, list[str]] | None = None, **kwargs) -> SafePageFetcher:
    return SafePageFetcher(resolver(addresses or {}), httpx.MockTransport(site), **kwargs)


def test_the_page_is_read_from_the_checked_address_with_our_user_agent() -> None:
    site = Site({("www.portal.example", "/p/1"): html(fixture("zonaprop_like"))})

    page = fetcher(site).fetch("https://www.portal.example/p/1")

    (request,) = site.requests
    assert request.url.host == PUBLIC  # connected to the address that was checked
    assert request.headers["host"] == "www.portal.example"
    assert request.extensions["sni_hostname"] == "www.portal.example"
    assert request.headers["user-agent"] == USER_AGENT == "inmo24x7/1.0 (+https://www.inmo24x7.com)"
    assert "cookie" not in request.headers
    assert "RealEstateListing" in page.html


@pytest.mark.parametrize(
    "url",
    [
        "ftp://www.portal.example/p",
        "https://www.portal.example:8443/p",
        "http://user:pass@www.portal.example/p",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://localhost/",
        "http://10.0.0.5/",
    ],
)
def test_urls_that_are_not_public_web_pages_are_refused_before_any_request(url: str) -> None:
    site = Site({})

    with pytest.raises(ListingUrlError):
        fetcher(site).fetch(url)

    assert site.requests == []


def test_a_host_that_resolves_to_a_private_address_is_refused() -> None:
    site = Site({})

    with pytest.raises(ListingUrlError):
        fetcher(site, {"intranet.portal.example": [PUBLIC, "192.168.1.10"]}).fetch(
            "https://intranet.portal.example/p"
        )

    assert site.requests == []


def test_a_redirect_to_a_private_address_is_refused() -> None:
    site = Site(
        {
            ("www.portal.example", "/p/1"): httpx.Response(
                302, headers={"location": "http://metadata.portal.example/latest"}
            )
        }
    )

    with pytest.raises(ListingUrlError):
        fetcher(site, {"metadata.portal.example": ["169.254.169.254"]}).fetch(
            "https://www.portal.example/p/1"
        )

    assert len(site.requests) == 1  # the redirect target was never requested


def test_redirects_are_followed_three_times_at_most() -> None:
    routes = {
        ("www.portal.example", f"/{n}"): httpx.Response(301, headers={"location": f"/{n + 1}"})
        for n in range(5)
    }
    site = Site(routes)

    with pytest.raises(ListingFetchError) as raised:
        fetcher(site).fetch("https://www.portal.example/0")

    assert raised.value.problem is ReadProblem.UNREACHABLE
    assert len(site.requests) == 4  # the URL and 3 redirects


def test_a_redirect_is_followed_without_the_cookies_it_set() -> None:
    site = Site(
        {
            ("www.portal.example", "/old"): httpx.Response(
                301, headers={"location": "/new", "set-cookie": "session=abc; Path=/"}
            ),
            ("www.portal.example", "/new"): html("<h1>ok</h1>"),
        }
    )

    page = fetcher(site).fetch("https://www.portal.example/old")

    assert page.url == "https://www.portal.example/new"
    assert "cookie" not in site.requests[1].headers


@pytest.mark.parametrize(
    ("response", "problem"),
    [
        (httpx.Response(403, text="Access denied"), ReadProblem.BLOCKED),
        (httpx.Response(429), ReadProblem.BLOCKED),
        (httpx.Response(404), ReadProblem.GONE),
        (httpx.Response(500), ReadProblem.UNREACHABLE),
        (
            httpx.Response(200, content=b"{}", headers={"content-type": "application/json"}),
            ReadProblem.NOT_HTML,
        ),
        (
            httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}),
            ReadProblem.NOT_HTML,
        ),
    ],
)
def test_responses_that_are_not_a_readable_page(response: httpx.Response, problem) -> None:
    site = Site({("www.portal.example", "/p"): response})

    with pytest.raises(ListingFetchError) as raised:
        fetcher(site).fetch("https://www.portal.example/p")

    assert raised.value.problem is problem
    assert len(site.requests) == 1  # one request, never a retry


def test_a_page_over_the_size_cap_is_not_read_whole() -> None:
    big = "<p>" + "x" * 5000 + "</p>"
    site = Site({("www.portal.example", "/p"): html(big)})

    with pytest.raises(ListingFetchError) as raised:
        fetcher(site, max_bytes=1000).fetch("https://www.portal.example/p")

    assert raised.value.problem is ReadProblem.TOO_LARGE


def test_a_declared_size_over_the_cap_is_refused_before_reading() -> None:
    site = Site({("www.portal.example", "/p"): html("<p>x</p>", **{"content-length": "9999999"})})

    with pytest.raises(ListingFetchError) as raised:
        fetcher(site).fetch("https://www.portal.example/p")

    assert raised.value.problem is ReadProblem.TOO_LARGE


def test_a_timeout_is_reported_as_such() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ListingFetchError) as raised:
        SafePageFetcher(resolver({}), httpx.MockTransport(slow)).fetch("https://x.example/p")

    assert raised.value.problem is ReadProblem.TIMEOUT


@pytest.mark.parametrize(
    ("address", "public"),
    [
        (PUBLIC, True),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("100.64.0.1", False),  # carrier-grade NAT
        ("169.254.169.254", False),
        ("::ffff:127.0.0.1", False),
        ("fd00::1", False),
        ("224.0.0.1", False),
        ("2606:4700::1111", True),
    ],
)
def test_public_addresses(address: str, public: bool) -> None:
    assert is_public_address(address) is public
