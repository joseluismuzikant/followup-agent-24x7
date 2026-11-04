"""Supabase Auth's own record of the user: `email_confirmed_at` is not in the access token,
so the API asks `GET /auth/v1/user` with the user's token (only when an owner claim is at
stake). Nothing here logs the token or the email."""

import logging

import httpx

logger = logging.getLogger("followup.identity")

TIMEOUT_SECONDS = 5.0


class SupabaseEmailConfirmation:
    def __init__(
        self, supabase_url: str, anon_key: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._url = f"{supabase_url.rstrip('/')}/auth/v1/user"
        self._anon_key = anon_key
        self._transport = transport

    def is_confirmed(self, access_token: str, email: str) -> bool:
        try:
            with httpx.Client(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
                response = client.get(
                    self._url,
                    headers={"apikey": self._anon_key, "Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError:
            logger.warning("email_confirmation_unreachable")
            return False
        if not response.is_success:
            logger.warning("email_confirmation_failed", extra={"status": response.status_code})
            return False
        try:
            user = response.json()
        except ValueError:
            return False
        if not isinstance(user, dict):
            return False
        same_email = str(user.get("email") or "").strip().lower() == email.strip().lower()
        return bool(user.get("email_confirmed_at")) and same_email


class DevEmailConfirmation:
    """`dev:<email>` tokens (local development only; production refuses AUTH_MODE=dev)."""

    def is_confirmed(self, access_token: str, email: str) -> bool:
        return access_token.startswith("dev:")
