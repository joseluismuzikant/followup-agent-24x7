from fastapi.testclient import TestClient
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository


def test_list_tenants_starts_empty(client: TestClient) -> None:
    response = client.get("/tenants")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "limit": 20,
        "total": 0,
        "total_pages": 0,
    }


def test_create_and_list_tenants(client: TestClient) -> None:
    created = client.post("/tenants", json={"name": "Inmobiliaria Ñandú"})

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Inmobiliaria Ñandú"
    assert body["slug"] == "inmobiliaria-nandu"
    assert body["id"]
    assert body["created_at"]

    listed = client.get("/tenants")
    assert listed.status_code == 200
    assert listed.json()["items"] == [body]
    assert listed.json()["total"] == 1
    assert listed.json()["total_pages"] == 1


def test_list_tenants_paginates(client: TestClient) -> None:
    for name in ("Inmobiliaria Uno", "Inmobiliaria Dos", "Inmobiliaria Tres"):
        assert client.post("/tenants", json={"name": name}).status_code == 201

    response = client.get("/tenants", params={"page": 2, "limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["page"] == 2
    assert body["limit"] == 2
    assert body["total"] == 3
    assert body["total_pages"] == 2


def test_list_tenants_rejects_invalid_pagination(client: TestClient) -> None:
    response = client.get("/tenants", params={"page": 0})

    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


def test_create_tenant_rejects_duplicate_name(client: TestClient) -> None:
    client.post("/tenants", json={"name": "Inmobiliaria Sur"})

    response = client.post("/tenants", json={"name": "Inmobiliaria Sur"})

    assert response.status_code == 409
    assert response.json() == {"code": "tenant_slug_taken"}


def test_create_tenant_rejects_blank_name(client: TestClient) -> None:
    response = client.post("/tenants", json={"name": "   "})

    assert response.status_code == 422
    assert response.json() == {"code": "tenant_name_invalid"}


def test_database_duplicate_returns_conflict(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        SqlAlchemyTenantRepository,
        "slug_exists",
        lambda _self, _slug: False,
    )

    first = client.post("/tenants", json={"name": "Inmobiliaria Sur"})
    second = client.post("/tenants", json={"name": "Inmobiliaria Sur"})

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"code": "tenant_slug_taken"}
