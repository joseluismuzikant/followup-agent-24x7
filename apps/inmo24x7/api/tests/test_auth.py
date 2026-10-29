from uuid import uuid4

from fastapi.testclient import TestClient


def _sign_up(client: TestClient, auth, email: str) -> tuple[str, dict]:
    user_id = uuid4()
    token = auth.register(user_id, email=email)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/me/sign-up",
        json={"business_name": f"Negocio {user_id}", "business_type": "inmobiliaria"},
        headers=headers,
    )
    assert response.status_code == 201
    return token, response.json()


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/me")

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}


def test_me_rejects_invalid_token(client: TestClient, auth) -> None:
    response = client.get(
        "/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}


def test_tenants_requires_platform_admin(client: TestClient, auth) -> None:
    token, _ = _sign_up(client, auth, "owner@example.com")

    response = client.get(
        "/tenants",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json() == {"code": "admin_required"}


def test_tenant_is_scoped_to_caller(client: TestClient, auth) -> None:
    token_a, body_a = _sign_up(client, auth, "a@example.com")
    token_b, body_b = _sign_up(client, auth, "b@example.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    tenant_a = client.get("/tenant", headers=headers_a).json()
    tenant_b = client.get("/tenant", headers=headers_b).json()

    assert tenant_a["id"] == body_a["tenant"]["id"]
    assert tenant_b["id"] == body_b["tenant"]["id"]
    assert tenant_a["id"] != tenant_b["id"]

    # A cannot list tenants, so it can never reach B's data.
    denied = client.get("/tenants", headers=headers_a)
    assert denied.status_code == 403
