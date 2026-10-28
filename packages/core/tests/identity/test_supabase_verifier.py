from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from followup_core.identity.domain.errors import InvalidTokenError
from followup_core.identity.infrastructure.supabase_verifier import SupabaseJwtVerifier

ISSUER = "https://example.supabase.co/auth/v1"
SECRET = "x" * 32


def _claims(**overrides):
    claims = {
        "sub": str(uuid4()),
        "email": "owner@example.com",
        "aud": "authenticated",
        "iss": ISSUER,
        "exp": 4_102_444_800,
    }
    claims.update(overrides)
    return claims


def test_hs256_token_is_verified() -> None:
    claims = _claims()
    token = jwt.encode(claims, SECRET, algorithm="HS256")

    verified = SupabaseJwtVerifier(secret=SECRET, issuer=ISSUER).verify(token)

    assert str(verified.user_id) == claims["sub"]
    assert verified.email == "owner@example.com"


def test_wrong_issuer_is_rejected() -> None:
    token = jwt.encode(_claims(iss="https://evil.example/auth/v1"), SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        SupabaseJwtVerifier(secret=SECRET, issuer=ISSUER).verify(token)


def test_wrong_audience_is_rejected() -> None:
    token = jwt.encode(_claims(aud="anon"), SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        SupabaseJwtVerifier(secret=SECRET, issuer=ISSUER).verify(token)


def test_non_uuid_subject_is_rejected() -> None:
    token = jwt.encode(_claims(sub="not-a-uuid"), SECRET, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        SupabaseJwtVerifier(secret=SECRET, issuer=ISSUER).verify(token)


def test_jwks_accepts_es256_and_reuses_one_client(monkeypatch) -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    created: list[str] = []

    class StubClient:
        def __init__(self, url: str) -> None:
            created.append(url)

        def get_signing_key_from_jwt(self, _token: str):
            return SimpleNamespace(key=private_key.public_key())

    monkeypatch.setattr(jwt, "PyJWKClient", StubClient)
    verifier = SupabaseJwtVerifier(jwks_url="https://example/jwks.json", issuer=ISSUER)

    for _ in range(3):
        token = jwt.encode(_claims(), private_key, algorithm="ES256")
        verifier.verify(token)

    assert created == ["https://example/jwks.json"]
