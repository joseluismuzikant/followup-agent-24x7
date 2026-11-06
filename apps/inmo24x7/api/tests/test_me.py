"""/me and the invitation-only sign-up."""

from uuid import uuid4

from fastapi.testclient import TestClient


def _invited(auth, name: str = "Inmobiliaria Sur") -> dict[str, str]:
    user_id = uuid4()
    email = f"{user_id}@example.com"
    auth.invite(email, name)
    return {"Authorization": f"Bearer {auth.register(user_id, email=email)}"}


def test_sign_up_joins_the_business_an_admin_created(client: TestClient, auth) -> None:
    response = client.post("/me/sign-up", headers=_invited(auth))

    assert response.status_code == 201
    body = response.json()
    assert body["profile"]["role"] == "owner"
    assert body["profile"]["is_platform_admin"] is False
    assert body["tenant"]["name"] == "Inmobiliaria Sur"
    assert body["tenant"]["status"] == "active"
    assert body["tenant"]["trial_ends_at"]


def test_an_email_nobody_invited_cannot_sign_up(client: TestClient, auth) -> None:
    user_id = uuid4()
    token = auth.register(user_id, email=f"{user_id}@example.com")

    response = client.post("/me/sign-up", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json() == {"code": "not_invited"}


def test_me_requires_profile(client: TestClient, auth) -> None:
    user_id = uuid4()
    token = auth.register(user_id, email=f"{user_id}@example.com")

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404
    assert response.json() == {"code": "profile_not_found"}


def test_me_returns_profile_and_tenant(client: TestClient, auth) -> None:
    headers = _invited(auth)
    client.post("/me/sign-up", headers=headers)

    response = client.get("/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["role"] == "owner"
    assert body["tenant"]["name"] == "Inmobiliaria Sur"


def test_sign_up_is_idempotent(client: TestClient, auth) -> None:
    headers = _invited(auth)

    first = client.post("/me/sign-up", headers=headers)
    second = client.post("/me/sign-up", headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["tenant"]["id"] == first.json()["tenant"]["id"]


def test_sign_up_requires_token(client: TestClient) -> None:
    response = client.post("/me/sign-up")

    assert response.status_code == 401
    assert response.json() == {"code": "unauthorized"}
