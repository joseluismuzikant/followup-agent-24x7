from collections.abc import Mapping
from uuid import UUID

import jwt

from ..domain.errors import InvalidTokenError
from ..domain.token_verifier import VerifiedToken


class SupabaseJwtVerifier:
    """Verifies Supabase access tokens (HS256 secret or RS256 JWKS)."""

    def __init__(
        self,
        *,
        secret: str | None = None,
        jwks_url: str | None = None,
        audience: str = "authenticated",
    ) -> None:
        self._secret = secret
        self._jwks_url = jwks_url
        self._audience = audience

    def verify(self, token: str) -> VerifiedToken:
        try:
            if self._secret:
                payload = jwt.decode(
                    token,
                    self._secret,
                    algorithms=["HS256"],
                    audience=self._audience,
                )
            elif self._jwks_url:
                client = jwt.PyJWKClient(self._jwks_url)
                signing_key = client.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self._audience,
                )
            else:
                raise InvalidTokenError("No token verification method configured.")
        except jwt.PyJWTError as error:
            raise InvalidTokenError("Invalid access token.") from error

        subject = payload.get("sub")
        email = payload.get("email")
        if not subject or not email:
            raise InvalidTokenError("Access token is missing required claims.")

        return VerifiedToken(user_id=UUID(subject), email=email)


class FakeTokenVerifier:
    """Deterministic verifier for local development and tests."""

    def __init__(
        self,
        mapping: Mapping[str, VerifiedToken] | None = None,
        default: VerifiedToken | None = None,
    ) -> None:
        self._mapping = dict(mapping or {})
        self._default = default

    def verify(self, token: str) -> VerifiedToken:
        identity = self._mapping.get(token, self._default)
        if identity is None:
            raise InvalidTokenError("Invalid access token.")
        return identity

    def register(self, token: str, identity: VerifiedToken) -> None:
        self._mapping[token] = identity
