"""POST /properties/from-link, /properties/from-text and /properties/{id}/refresh-from-link
against the test database. Portals are a mocked web (saved HTML written for the tests) and
the model is the fake: no network, no real LLM."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from inmo24x7_api.container import get_listing_model, get_page_fetcher
from inmo24x7_api.main import app
from inmo24x7_api.properties.domain.listing import LINK_READS_PER_HOUR
from inmo24x7_api.properties.domain.property import (
    Currency,
    Operation,
    Property,
    PropertyFields,
    PropertyOrigin,
)
from inmo24x7_api.properties.infrastructure.listing_model import FakeListingModel
from inmo24x7_api.properties.infrastructure.page_fetcher import SafePageFetcher
from sqlalchemy import text
from test_listing_reading import PUBLIC, Site, fixture, html
from test_setup_endpoints import Account, _set_role

ZONAPROP = "https://www.zonaprop.com.ar/propiedades/clasificado/alclapin-2-amb-gorriti-55555.html"
TOKKO_LIKE = "https://www.inmobiliaria.example/p/remax"

# A Zonaprop listing as an agent would copy it from the phone (written for the tests).
PASTED_ZONAPROP = """Iniciar sesión
Publicar
Alquiler
$ 780.000
Expensas $ 60.000
Departamento · 2 ambientes · 45 m²
Dirección: Gorriti 4800
Barrio: Palermo
Luminoso 2 ambientes con balcón al frente.
Seguro de caución o garantía propietaria. Contrato de 24 meses. Acepta mascotas.
Compartir
Denunciar aviso
"""


class Web:
    """The test's mocked internet and model, set on the app."""

    def __init__(self) -> None:
        self.site = Site({})
        self.model = FakeListingModel()
        self.addresses: dict[str, list[str]] = {}

    def serve(self, url: str, response: httpx.Response) -> None:
        parts = httpx.URL(url)
        self.site.routes[(parts.host, parts.path)] = response

    def fetcher(self) -> SafePageFetcher:
        return SafePageFetcher(
            lambda host, port: self.addresses.get(host, [PUBLIC]),
            httpx.MockTransport(self.site),
        )


@pytest.fixture
def web(client: TestClient):
    world = Web()
    app.dependency_overrides[get_page_fetcher] = world.fetcher
    app.dependency_overrides[get_listing_model] = lambda: world.model
    return world


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


def from_link(account: Account, url: str):
    return account.post("/properties/from-link", {"url": url})


def from_text(account: Account, pasted: str, link: str = ZONAPROP):
    return account.post("/properties/from-text", {"text": pasted, "link": link})


def test_a_listing_page_becomes_a_draft_and_nothing_is_saved(owner: Account, web: Web) -> None:
    web.serve(ZONAPROP, html(fixture("zonaprop_like")))

    response = from_link(owner, ZONAPROP + "?utm_source=whatsapp&fbclid=abc")

    assert response.status_code == 200
    draft = response.json()
    assert draft["link"] == ZONAPROP  # without the tracking parameters
    assert {key: draft[key] for key in ("title", "address", "operation", "zone")} == {
        "title": "2 ambientes luminoso con balcón",
        "address": "Gorriti 4800",
        "operation": "rent",
        "zone": "Palermo",
    }
    assert (draft["price"], draft["currency"], draft["rooms"]) == (850_000, "ARS", 2)
    assert draft["conditions"]["garantias"] == ["caucion", "propietaria"]
    assert draft["conditions"]["mascotas"] is True
    assert draft["image_url"] == "https://img.portal.example/gorriti-4800/1.jpg"
    assert set(draft["sources"].values()) == {"structured"}
    assert draft["problem"] is None and draft["duplicate"] is None
    assert web.model.texts == []  # the structured data was enough: no model call
    assert owner.get("/properties").json()["total"] == 0


def test_the_model_reads_what_the_page_does_not_structure(
    owner: Account, web: Web, db_session
) -> None:
    url = "https://www.inmo.example/ph-thames"
    web.serve(url, html(fixture("text_only")))

    draft = from_link(owner, url).json()

    assert draft["title"] == "Hermoso PH reciclado"
    assert draft["sources"]["title"] == "structured"
    assert (draft["price"], draft["currency"], draft["address"]) == (1_100_000, "ARS", "Thames 600")
    assert {draft["sources"][name] for name in ("price", "address", "operation", "rooms")} == {
        "model"
    }
    (sent,) = web.model.texts
    assert "no debe leerse" not in sent and len(sent) <= 8_000
    # Recorded like any model call: no thread, the panel's channel.
    (row,) = db_session.execute(
        text("SELECT operation, channel, thread_id, model FROM llm_usage")
    ).all()
    assert tuple(row) == ("read_listing", "panel", None, "fake:fake")


def test_a_blocked_portal_still_opens_the_form_with_the_link(owner: Account, web: Web) -> None:
    web.serve(ZONAPROP, httpx.Response(403, text="<html>Access denied</html>"))

    draft = from_link(owner, ZONAPROP).json()

    assert draft["problem"] == "blocked"
    assert draft["portal"] == "Zonaprop"
    assert draft["message"] == (
        "Zonaprop no deja leer la página. Abrí tu publicación, seleccioná todo (Ctrl+A), "
        "copiá (Ctrl+C) y pegalo acá."
    )
    assert draft["link"] == ZONAPROP and draft["title"] == ""
    assert len(web.site.requests) == 1  # one request: never a retry or another user agent
    assert web.site.requests[0].headers["user-agent"].startswith("inmo24x7/1.0")


@pytest.mark.parametrize(
    ("response", "problem"),
    [
        (httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}),
         "not_html"),
        (html("<html><body><h1>Bienvenido</h1><p>Somos una inmobiliaria.</p></body></html>"),
         "not_listing"),
        (httpx.Response(404), "gone"),
    ],
)  # fmt: skip
def test_pages_that_are_not_a_listing_say_why(
    owner: Account, web: Web, response: httpx.Response, problem: str
) -> None:
    url = "https://www.inmo.example/p/1"
    web.serve(url, response)

    draft = from_link(owner, url).json()

    assert draft["problem"] == problem and draft["message"]
    assert draft["link"] == url


def test_a_redirect_to_a_private_address_is_refused(owner: Account, web: Web) -> None:
    url = "https://www.inmo.example/p/1"
    web.serve(url, httpx.Response(302, headers={"location": "http://internal.inmo.example/"}))
    web.addresses["internal.inmo.example"] = ["10.0.0.7"]

    response = from_link(owner, url)

    assert response.status_code == 422
    assert response.json()["code"] == "listing_url_invalid"
    assert len(web.site.requests) == 1


def test_a_page_over_the_size_cap_is_refused(owner: Account, web: Web) -> None:
    url = "https://www.inmo.example/p/1"
    web.serve(url, html("<p>x</p>", **{"content-length": str(4 * 1024 * 1024)}))

    assert from_link(owner, url).json()["problem"] == "too_large"


def test_a_link_already_loaded_offers_the_property(owner: Account, web: Web) -> None:
    created = owner.post(
        "/properties",
        {
            "title": "2 ambientes luminoso",
            "address": "Gorriti 4800",
            "operation": "rent",
            "zone": "Palermo",
            "price": 850_000,
            "rooms": 2,
            "link": ZONAPROP,
        },
    ).json()

    draft = from_link(owner, ZONAPROP + "?utm_campaign=x").json()

    assert draft["duplicate"]["id"] == created["id"]
    assert web.site.requests == []  # not read again
    assert from_text(owner, PASTED_ZONAPROP).json()["duplicate"]["id"] == created["id"]


def test_a_pasted_zonaprop_text_becomes_a_draft_read_by_the_model(owner: Account, web: Web) -> None:
    response = from_text(owner, PASTED_ZONAPROP)

    assert response.status_code == 200
    draft = response.json()
    assert (draft["operation"], draft["price"], draft["currency"]) == ("rent", 780_000, "ARS")
    assert (draft["rooms"], draft["zone"], draft["address"]) == (2, "Palermo", "Gorriti 4800")
    assert draft["conditions"]["garantias"] == ["caucion", "propietaria"]
    assert draft["conditions"]["contrato_minimo_meses"] == 24
    assert draft["link"] == ZONAPROP
    # Everything comes from the model here: every field is marked "Revisá este dato".
    assert set(draft["sources"].values()) == {"model"}
    # The page's menus and buttons never reach the model.
    (sent,) = web.model.texts
    assert "Iniciar sesión" not in sent and "Denunciar aviso" not in sent
    assert web.site.requests == []


@pytest.mark.parametrize("pasted", ["", "   ", "Iniciar sesión\nCompartir", "Alquiler $ 500"])
def test_an_empty_or_too_short_text_is_refused(owner: Account, web: Web, pasted: str) -> None:
    response = from_text(owner, pasted)

    assert response.status_code == 422
    assert response.json()["code"] == "listing_text_too_short"
    assert web.model.texts == []


def test_the_text_needs_a_valid_link(owner: Account, web: Web) -> None:
    response = from_text(owner, PASTED_ZONAPROP, link="zonaprop")

    assert response.json()["code"] == "listing_url_invalid"


def test_when_the_model_fails_the_draft_says_so(owner: Account, web: Web) -> None:
    web.model.fail = True

    draft = from_text(owner, PASTED_ZONAPROP).json()

    assert draft["title"] == "" and draft["link"] == ZONAPROP
    assert draft["warnings"] == [
        "No pudimos completar los datos con IA ahora. Completá lo que falta a mano."
    ]


@pytest.mark.parametrize("role", ["agent", "viewer"])
def test_only_owners_and_managers_read_links(
    owner: Account, web: Web, db_session, role: str
) -> None:
    _set_role(db_session, owner.user_id, role)

    assert from_link(owner, ZONAPROP).status_code == 403
    assert from_text(owner, PASTED_ZONAPROP).status_code == 403


def test_reads_are_limited_per_agency_and_hour(
    client: TestClient, auth, owner: Account, web: Web, db_session
) -> None:
    db_session.execute(
        text(
            "INSERT INTO audit_events (id, tenant_id, at, actor_kind, action, details) "
            "SELECT gen_random_uuid(), :tenant, now(), 'user', 'property_link_read', '{}' "
            "FROM generate_series(1, :count)"
        ),
        {"tenant": owner.tenant_id, "count": LINK_READS_PER_HOUR},
    )
    db_session.commit()
    web.serve(ZONAPROP, html(fixture("zonaprop_like")))

    assert from_link(owner, ZONAPROP).json()["code"] == "listing_read_limit"
    assert from_text(owner, PASTED_ZONAPROP).status_code == 429
    assert web.site.requests == [] and web.model.texts == []
    # Another agency has its own count.
    other = Account(client, auth, "Inmobiliaria Norte")
    assert from_link(other, ZONAPROP).status_code == 200


def test_each_read_is_audited_without_the_link(owner: Account, web: Web, db_session) -> None:
    web.serve(ZONAPROP, html(fixture("zonaprop_like")))
    from_link(owner, ZONAPROP)

    (row,) = db_session.execute(
        text(
            "SELECT details::text AS details FROM audit_events WHERE action = 'property_link_read'"
        )
    ).all()
    assert row.details == '{"code": "read", "source": "structured"}'


# "Actualizar desde el link".


def _manual(owner: Account, **overrides) -> dict:
    body = {
        "title": "2 ambientes luminoso",
        "address": "Gorriti 4800",
        "operation": "rent",
        "zone": "Palermo",
        "price": 800_000,
        "rooms": 2,
        "link": ZONAPROP,
    }
    body.update(overrides)
    return owner.post("/properties", body).json()


def refresh(account: Account, property_id: str, pasted: str | None = None):
    return account.post(f"/properties/{property_id}/refresh-from-link", {"text": pasted})


def test_refreshing_shows_what_changed_and_saves_nothing(owner: Account, web: Web) -> None:
    item = _manual(owner)
    web.serve(ZONAPROP, html(fixture("zonaprop_like")))

    result = refresh(owner, item["id"]).json()

    title = {"current": "2 ambientes luminoso", "read": "2 ambientes luminoso con balcón"}
    assert result["changes"] == [
        {"field": "title", **title},
        {"field": "price", "current": 800_000, "read": 850_000},
    ]
    assert result["draft"]["price"] == 850_000
    assert owner.get("/properties").json()["items"][0]["price"] == 800_000


def test_a_publication_that_is_gone_suggests_pausing(owner: Account, web: Web) -> None:
    item = _manual(owner)
    web.serve(ZONAPROP, httpx.Response(410))

    result = refresh(owner, item["id"]).json()

    assert result["changes"] == [{"field": "status", "current": "published", "read": "paused"}]
    assert result["draft"]["problem"] == "gone"


def test_a_blocked_portal_can_be_refreshed_from_a_pasted_text(owner: Account, web: Web) -> None:
    item = _manual(owner, price=700_000)
    web.serve(ZONAPROP, httpx.Response(403))

    assert refresh(owner, item["id"]).json()["draft"]["problem"] == "blocked"
    result = refresh(owner, item["id"], PASTED_ZONAPROP).json()

    assert {"field": "price", "current": 700_000, "read": 780_000} in result["changes"]
    assert result["draft"]["sources"]["price"] == "model"


def test_tokko_properties_are_not_refreshed_from_their_link(
    owner: Account, web: Web, db_session
) -> None:
    from inmo24x7_api.properties.infrastructure.repositories import SqlAlchemyPropertyRepository

    now = datetime.now(UTC)
    tokko = Property(
        uuid4(),
        owner.tenant_id,
        PropertyFields(
            "Casa", "Los Robles 350", Operation.SALE, "Pilar", 320_000, Currency.USD, 4, TOKKO_LIKE
        ),
        now,
        now,
        source=PropertyOrigin.TOKKO,
        external_id="123",
    )
    SqlAlchemyPropertyRepository(db_session).add(tokko)
    db_session.commit()

    response = refresh(owner, str(tokko.id))

    assert response.status_code == 409
    assert response.json()["code"] == "property_managed_by_tokko"
    assert refresh(owner, str(uuid4())).status_code == 404
