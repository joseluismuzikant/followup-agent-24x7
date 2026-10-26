from fastapi.testclient import TestClient


def test_list_tenants_starts_empty(client: TestClient) -> None:
    response = client.get("/tenants")

    assert response.status_code == 200
    assert response.json() == []


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
    assert listed.json() == [body]


def test_create_tenant_rejects_duplicate_name(client: TestClient) -> None:
    client.post("/tenants", json={"name": "Inmobiliaria Sur"})

    response = client.post("/tenants", json={"name": "Inmobiliaria Sur"})

    assert response.status_code == 409
    assert response.json()["detail"] == "Ya existe un negocio con ese nombre."


def test_create_tenant_rejects_blank_name(client: TestClient) -> None:
    response = client.post("/tenants", json={"name": "   "})

    assert response.status_code == 422
