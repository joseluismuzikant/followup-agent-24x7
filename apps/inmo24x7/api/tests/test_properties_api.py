"""S7 endpoints against the test database: scoping, roles, import and the agent's search."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from inmo24x7_api.properties.domain.search import PropertyQuery
from inmo24x7_api.properties.infrastructure.repositories import (
    SqlAlchemyPropertyRepository,
    TenantPropertySearch,
)
from sqlalchemy import text
from test_setup_endpoints import Account, _set_role

SAMPLES = Path(__file__).resolve().parents[4] / "docs" / "samples"


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


def _property(**overrides) -> dict:
    body = {
        "title": "2 ambientes luminoso",
        "address": "Gorriti 4800",
        "operation": "rent",
        "zone": "Palermo",
        "price": 850_000,
        "rooms": 2,
        "link": f"https://www.inmobiliariasur.example/p/{uuid4()}",
    }
    body.update(overrides)
    return body


def _import(account: Account, name: str, content: bytes | None = None):
    data = content if content is not None else (SAMPLES / name).read_bytes()
    return account.client.post(
        "/properties/import", files={"file": (name, data)}, headers=account.headers
    )


def _patch(account: Account, property_id: str, body: dict):
    return account.client.patch(f"/properties/{property_id}", json=body, headers=account.headers)


def test_create_list_edit_publish_and_pause(owner: Account) -> None:
    created = owner.post("/properties", _property())
    assert created.status_code == 201
    item = created.json()
    # Rents default to pesos and new properties are published.
    assert (item["currency"], item["status"], item["inquiries"]) == ("ARS", "published", 0)

    edited = _patch(owner, item["id"], {"price": 900_000, "title": "  2 amb.  reciclado "})
    assert edited.status_code == 200
    assert (edited.json()["price"], edited.json()["title"]) == (900_000, "2 amb. reciclado")

    paused = owner.post(f"/properties/{item['id']}/pause", {})
    assert paused.json()["status"] == "paused"
    assert owner.post(f"/properties/{item['id']}/publish", {}).json()["status"] == "published"

    listing = owner.get("/properties").json()
    assert (listing["total"], listing["page"], listing["page_size"]) == (1, 1, 20)
    assert listing["items"][0]["price"] == 900_000


@pytest.mark.parametrize(
    "changes",
    [
        {"price": 0},
        {"rooms": 0},
        {"link": "www.sin-esquema.com"},
        {"link": "/ejemplo/relativo"},
        {"title": "   "},
    ],
)
def test_invalid_properties_are_rejected(owner: Account, changes: dict) -> None:
    response = owner.post("/properties", _property(**changes))

    assert response.status_code == 422
    assert response.json() == {"code": "property_invalid"}


def test_links_are_unique_per_tenant(client: TestClient, auth, owner: Account) -> None:
    link = "https://www.inmobiliariasur.example/p/unica"
    first = owner.post("/properties", _property(link=link)).json()
    other = owner.post("/properties", _property()).json()

    assert owner.post("/properties", _property(link=link)).json() == {"code": "property_link_taken"}
    assert _patch(owner, other["id"], {"link": link}).status_code == 409
    # Another tenant may list the same URL.
    assert (
        Account(client, auth, "Otra").post("/properties", _property(link=link)).status_code == 201
    )
    assert first["link"] == link


def test_tenants_never_see_or_edit_each_others_properties(
    client: TestClient, auth, owner: Account
) -> None:
    item = owner.post("/properties", _property()).json()
    other = Account(client, auth, "Agencia B")

    assert other.get("/properties").json()["total"] == 0
    assert _patch(other, item["id"], {"price": 1}).json() == {"code": "property_not_found"}
    assert other.post(f"/properties/{item['id']}/pause", {}).status_code == 404


@pytest.mark.parametrize("role", ["agent", "viewer"])
def test_only_owners_and_managers_write(owner: Account, db_session, role: str) -> None:
    item = owner.post("/properties", _property()).json()
    _set_role(db_session, owner.user_id, role)

    assert owner.get("/properties").status_code == 200
    assert owner.post("/properties", _property()).status_code == 403
    assert _patch(owner, item["id"], {"price": 1}).status_code == 403
    assert owner.post(f"/properties/{item['id']}/pause", {}).status_code == 403
    assert _import(owner, "propiedades.csv").status_code == 403


def test_manager_can_write(owner: Account, db_session) -> None:
    _set_role(db_session, owner.user_id, "manager")

    assert owner.post("/properties", _property()).status_code == 201


def test_search_is_accent_insensitive_and_filters_combine(owner: Account) -> None:
    _import(owner, "propiedades.csv")

    nunez = owner.get("/properties?search=nunez").json()
    assert {item["zone"] for item in nunez["items"]} == {"Núñez"}
    # "AREVALO" finds "Arévalo 2100" by address.
    by_street = owner.get("/properties?search=AREVALO").json()["items"]
    assert [item["address"] for item in by_street] == ["Arévalo 2100"]
    rents = owner.get("/properties?search=palermo&operation=rent").json()
    assert rents["total"] == 4
    assert {item["operation"] for item in rents["items"]} == {"rent"}
    assert owner.get("/properties?status=paused").json()["total"] == 1


def test_pages_hold_20_properties(owner: Account) -> None:
    _import(owner, "propiedades.csv")
    for n in range(3):
        owner.post("/properties", _property(title=f"Extra {n}"))

    first = owner.get("/properties").json()
    second = owner.get("/properties?page=2").json()

    assert (first["total"], len(first["items"]), len(second["items"])) == (23, 20, 3)
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


def test_import_report_errors_csv_and_template(owner: Account) -> None:
    good = _import(owner, "propiedades.csv")
    assert good.status_code == 200
    assert {k: good.json()[k] for k in ("total", "imported", "created", "failed")} == {
        "total": 20,
        "imported": 20,
        "created": 20,
        "failed": 0,
    }

    bad = _import(owner, "propiedades-con-errores.csv").json()
    assert (bad["imported"], bad["total"], bad["failed"]) == (2, 5, 3)
    assert bad["errors"] == [
        "Fila 3: falta el precio.",
        "Fila 5: el link no es una dirección web válida.",
        "Fila 6: la operación tiene que ser «venta» o «alquiler».",
    ]

    download = owner.get(f"/properties/import/{bad['id']}/errors.csv")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert "attachment" in download.headers["content-disposition"]
    lines = download.content.decode("utf-8-sig").splitlines()
    assert lines[0].endswith(",estado,error")
    assert len(lines) == 4

    template = owner.get("/properties/import-template.csv")
    assert template.content.decode("utf-8-sig").startswith("titulo,direccion,operacion")


def test_xlsx_import(owner: Account) -> None:
    report = _import(owner, "propiedades.xlsx").json()

    assert (report["imported"], report["failed"]) == (20, 0)


def test_import_errors_are_scoped_to_the_tenant(client: TestClient, auth, owner: Account) -> None:
    bad = _import(owner, "propiedades-con-errores.csv").json()
    other = Account(client, auth, "Agencia B")

    assert other.get(f"/properties/import/{bad['id']}/errors.csv").json() == {
        "code": "import_not_found"
    }


def test_invalid_and_too_large_files(owner: Account) -> None:
    assert _import(owner, "x.csv", b"nombre,precio\nCasa,1\n").json() == {
        "code": "import_file_invalid"
    }
    too_large = _import(owner, "x.csv", b"a" * (5 * 1024 * 1024 + 1))
    assert (too_large.status_code, too_large.json()) == (413, {"code": "import_too_large"})


def test_first_import_completes_the_checklist_item(owner: Account) -> None:
    assert owner.get("/onboarding").json()["checklist"]["facts"]["own_properties"] is False

    _import(owner, "propiedades.csv")

    assert owner.get("/onboarding").json()["checklist"]["facts"]["own_properties"] is True


def test_inquiries_count_distinct_real_leads(owner: Account, db_session) -> None:
    _import(owner, "propiedades.csv")
    # A simulator conversation shows properties but is a test, so it does not count.
    for message in ["Hola", "Quiero alquilar", "Palermo"]:
        owner.post("/simulator/messages", {"text": message})
    (lead_id,) = db_session.execute(text("SELECT id FROM leads")).scalars()
    shown = db_session.execute(text("SELECT property_id FROM lead_property_matches")).scalars()
    shown_ids = {str(item) for item in shown}
    assert shown_ids

    def inquiries() -> dict[str, int]:
        items = owner.get("/properties?search=palermo&operation=rent").json()["items"]
        return {item["id"]: item["inquiries"] for item in items}

    assert set(inquiries().values()) == {0}
    db_session.execute(text("UPDATE leads SET is_test = false WHERE id = :id"), {"id": lead_id})
    db_session.commit()
    counted = inquiries()
    assert {key for key, value in counted.items() if value == 1} == shown_ids


def test_search_uses_only_published_own_properties_and_falls_back_to_samples(
    client: TestClient, auth, owner: Account, db_session
) -> None:
    other = Account(client, auth, "Agencia B")
    other.post("/properties", _property(link="https://otra.example/p/1"))
    search = TenantPropertySearch(SqlAlchemyPropertyRepository(db_session))
    query = PropertyQuery(zone="Palermo")

    # No own properties yet (the other tenant's never count): sample listings.
    assert all(match.listing.is_sample for match in search.search(owner.tenant_id, query))

    item = owner.post("/properties", _property(link="https://inmo.example/p/1")).json()
    db_session.expire_all()
    results = search.search(owner.tenant_id, query)
    assert [(m.listing.id, m.listing.link) for m in results] == [
        (item["id"], "https://inmo.example/p/1")
    ]

    # Paused properties are never shown; with nothing published the samples come back.
    owner.post(f"/properties/{item['id']}/pause", {})
    db_session.expire_all()
    assert all(match.listing.is_sample for match in search.search(owner.tenant_id, query))
    assert search.uses_samples(owner.tenant_id)


def test_simulator_banner_and_cards_follow_own_published_properties(owner: Account) -> None:
    assert owner.get("/simulator").json()["uses_sample_properties"] is True
    _import(owner, "propiedades.csv")

    for message in ["Hola", "Quiero alquilar"]:
        owner.post("/simulator/messages", {"text": message})
    reply = owner.post("/simulator/messages", {"text": "Palermo"}).json()

    assert owner.get("/simulator").json()["uses_sample_properties"] is False
    cards = next(m["cards"] for m in reply["messages"] if m["cards"])
    assert cards and all(
        card["link"].startswith("https://www.inmobiliariasur.example/") and not card["is_sample"]
        for card in cards
    )
