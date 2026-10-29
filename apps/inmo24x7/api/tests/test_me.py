from uuid import uuid4

from fastapi.testclient import TestClient


def _token(auth) -> str:
    user_id = uuid4()
    return auth.register(user_id, email=f"{user_id}@example.com")


def test_sign_up_creates_profile_and_tenant(client: TestClient, auth) -> None:
    token = _token(auth)
    response = client.post(
        "/me/sign-up",
        json={"business_name": "Inmobiliaria Sur", "business_type": "inmobiliaria"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["profile"]["role"] == "owner"
    assert body["profile"]["is_platform_admin"] is False
    assert body["tenant"]["name"] == "Inmobiliaria Sur"
    assert body["tenant"]["status"] == "active"
    assert body["tenant"]["trial_ends_at"]


def test_me_requires_profile(client: TestClient, auth) -> None:
    token = _token(auth)

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json() == {"code": "profile_not_found"}


def test_me_returns_profile_and_tenant(client: TestClient, auth) -> None:
    token = _token(auth)
    headers = {"Authorization": f"Bearer {token}"}
    client.post(
        "/me/sign-up",
        json={"business_name": "Inmobiliaria Sur", "business_type": "inmobiliaria"},
        headers=headers,
    )

    response = client.get("/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["role"] == "owner"
    assert body["tenant"]["name"] == "Inmobiliaria Sur"


def test_sign_up_is_idempotent(client: TestClient, auth) -> None:
    token = _token(auth)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        "/me/sign-up",
        json={"business_name": "Inmobiliaria Sur", "business_type": "inmobiliaria"},
        headers=headers,
    )
    second = client.post(
        "/me/sign-up",
        json={"business_name": "Otro nombre", "business_type": "inmobiliaria"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["tenant"]["id"] == first.json()["tenant"]["id"]


def test_sign_up_requires_token(client: TestClient) -> None:
    response = client.post(
        "/me/sign-up", json={"business_name": "Inmobiliaria Sur", "business_type": "inmobiliaria"}
    )

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}


def test_sign_up_rejects_blank_business_name(client: TestClient, auth) -> None:
    token = _token(auth)

    response = client.post(
        "/me/sign-up",
        json={"business_name": "   ", "business_type": "inmobiliaria"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json() == {"code": "tenant_name_invalid"}


def test_sign_up_rejects_unknown_business_type(client: TestClient, auth) -> None:
    token = _token(auth)

    response = client.post(
        "/me/sign-up",
        json={"business_name": "Inmobiliaria Sur", "business_type": "pizzeria"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    assert response.json() == {"code": "business_type_invalid"}


def test_sign_up_with_a_taken_business_name_gets_the_next_free_slug(
    client: TestClient, auth
) -> None:
    slugs = []
    for _ in range(2):
        token = _token(auth)
        response = client.post(
            "/me/sign-up",
            json={"business_name": "Inmobiliaria Sur", "business_type": "inmobiliaria"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        slugs.append(response.json()["tenant"]["slug"])

    assert slugs == ["inmobiliaria-sur", "inmobiliaria-sur-2"]
