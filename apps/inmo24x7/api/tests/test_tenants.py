from uuid import uuid4

from fastapi.testclient import TestClient
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository


def _admin_headers(client: TestClient, auth) -> dict[str, str]:
    user_id = uuid4()
    token = auth.register(user_id, email="admin@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/me/sign-up",
        json={"business_name": "Inmobiliaria Admin"},
        headers=headers,
    )
    auth.make_admin(user_id)
    return headers


def test_list_tenants_starts_with_only_the_admin_tenant(
    client: TestClient,
    auth,
) -> None:
    response = client.get("/tenants", headers=_admin_headers(client, auth))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["total_pages"] == 1
    assert body["items"][0]["name"] == "Inmobiliaria Admin"


def test_create_and_list_tenants(client: TestClient, auth) -> None:
    headers = _admin_headers(client, auth)

    created = client.post(
        "/tenants",
        json={"name": "Inmobiliaria Ñandú"},
        headers=headers,
    )

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Inmobiliaria Ñandú"
    assert body["slug"] == "inmobiliaria-nandu"
    assert body["status"] == "active"
    assert body["trial_ends_at"]
    assert body["id"]

    listed = client.get("/tenants", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert body in listed.json()["items"]


def test_list_tenants_paginates(client: TestClient, auth) -> None:
    headers = _admin_headers(client, auth)
    for name in ("Inmobiliaria Uno", "Inmobiliaria Dos", "Inmobiliaria Tres"):
        assert client.post("/tenants", json={"name": name}, headers=headers).status_code == 201

    response = client.get("/tenants", params={"page": 2, "limit": 2}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["page"] == 2
    assert body["limit"] == 2
    assert body["total"] == 4
    assert body["total_pages"] == 2


def test_list_tenants_rejects_invalid_pagination(client: TestClient, auth) -> None:
    headers = _admin_headers(client, auth)

    response = client.get("/tenants", params={"page": 0}, headers=headers)

    assert response.status_code == 422
    assert response.json() == {"code": "validation_error"}


def test_create_tenant_rejects_duplicate_name(client: TestClient, auth) -> None:
    headers = _admin_headers(client, auth)
    client.post("/tenants", json={"name": "Inmobiliaria Sur"}, headers=headers)

    response = client.post("/tenants", json={"name": "Inmobiliaria Sur"}, headers=headers)

    assert response.status_code == 409
    assert response.json() == {"code": "tenant_slug_taken"}


def test_create_tenant_rejects_blank_name(client: TestClient, auth) -> None:
    headers = _admin_headers(client, auth)

    response = client.post("/tenants", json={"name": "   "}, headers=headers)

    assert response.status_code == 422
    assert response.json() == {"code": "tenant_name_invalid"}


def test_database_duplicate_returns_conflict(
    client: TestClient,
    auth,
    monkeypatch,
) -> None:
    headers = _admin_headers(client, auth)
    monkeypatch.setattr(
        SqlAlchemyTenantRepository,
        "slug_exists",
        lambda _self, _slug: False,
    )

    first = client.post("/tenants", json={"name": "Inmobiliaria Sur"}, headers=headers)
    second = client.post("/tenants", json={"name": "Inmobiliaria Sur"}, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"code": "tenant_slug_taken"}
