"""Where passwords live: Supabase Auth (its admin API, with the service-role key) or, in
AUTH_MODE=dev, a local table. Nothing here logs a password or an email."""

import base64
import hashlib
import hmac
import logging
import secrets
from uuid import UUID

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..domain.errors import AccountConflictError, IdentityError
from .dev_verifier import dev_user_id
from .models import DevPasswordModel

logger = logging.getLogger("followup.identity")

TIMEOUT_SECONDS = 8.0


class AccountDirectoryError(IdentityError):
    """The auth provider could not be reached or refused the change."""


class SupabaseAccountDirectory:
    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._url = f"{supabase_url.rstrip('/')}/auth/v1/admin/users"
        self._key = service_role_key
        self._transport = transport

    def _request(self, method: str, url: str, body: dict[str, object]) -> httpx.Response:
        if not self._key:
            raise AccountDirectoryError("SUPABASE_SERVICE_ROLE_KEY is not set.")
        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
                return client.request(
                    method,
                    url,
                    json=body,
                    headers={"apikey": self._key, "Authorization": f"Bearer {self._key}"},
                )
        except httpx.HTTPError as error:
            logger.warning("account_directory_unreachable")
            raise AccountDirectoryError("Supabase Auth unreachable.") from error

    def create_user(self, email: str, password: str) -> UUID:
        # Confirmed from the start: the admin vouches for the email, and the invitation
        # link proves it before the person sets their own password.
        response = self._request(
            "POST", self._url, {"email": email, "password": password, "email_confirm": True}
        )
        if response.status_code == 422 and "email_exists" in response.text:
            raise AccountConflictError(email)
        if not response.is_success:
            logger.warning("account_create_failed", extra={"status": response.status_code})
            raise AccountDirectoryError(f"Supabase Auth answered {response.status_code}.")
        return UUID(str(response.json()["id"]))

    def set_password(self, user_id: UUID, email: str, password: str) -> None:
        response = self._request("PUT", f"{self._url}/{user_id}", {"password": password})
        if not response.is_success:
            logger.warning("account_password_failed", extra={"status": response.status_code})
            raise AccountDirectoryError(f"Supabase Auth answered {response.status_code}.")


# scrypt with the standard library: fine for a development table nobody exposes.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def password_matches(password: str, stored: str) -> bool:
    salt_b64, _, digest_b64 = stored.partition("$")
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


class DevAccountDirectory:
    """AUTH_MODE=dev: user ids are the dev verifier's (one per email) and passwords are
    hashed in `dev_passwords`. The settings refuse dev mode in production."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _save(self, email: str, password: str) -> None:
        email = email.strip().lower()
        hashed = hash_password(password)
        self._session.execute(
            insert(DevPasswordModel)
            .values(email=email, password_hash=hashed)
            .on_conflict_do_update(index_elements=["email"], set_={"password_hash": hashed})
        )
        self._session.flush()

    def create_user(self, email: str, password: str) -> UUID:
        self._save(email, password)
        return dev_user_id(email)

    def set_password(self, user_id: UUID, email: str, password: str) -> None:
        self._save(email, password)

    def verify(self, email: str, password: str) -> bool:
        model = self._session.get(DevPasswordModel, email.strip().lower())
        return model is not None and password_matches(password, model.password_hash)
