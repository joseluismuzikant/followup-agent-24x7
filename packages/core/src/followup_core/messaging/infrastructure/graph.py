"""The Meta Graph API (WhatsApp Cloud API) over httpx. Tests mock it at the HTTP level with
httpx.MockTransport; nothing here logs a token, a phone number or message text."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from ..application.connections import PhoneInfo
from ..domain.connection import WhatsAppConnection
from ..domain.outbound import SendError, template_body
from .crypto import TokenCipher

logger = logging.getLogger("followup.whatsapp")

DEFAULT_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v26.0"
TIMEOUT_SECONDS = 10.0
# Meta error codes that mean "try again later" even with a 4xx status.
_RETRYABLE_CODES = frozenset({"4", "80007", "130429", "131016", "131048", "131056", "133004"})


@dataclass(frozen=True, slots=True)
class PhoneNumberInfo:
    display_phone_number: str
    verified_name: str


class GraphApiError(SendError):
    pass


class GraphClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_version: str = DEFAULT_API_VERSION,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/{api_version}",
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    def _request(
        self, method: str, path: str, token: str, json: Mapping[str, Any] | None = None, **kw: Any
    ) -> dict[str, Any]:
        try:
            response = self._client.request(
                method, path, json=json, headers={"Authorization": f"Bearer {token}"}, **kw
            )
        except httpx.HTTPError as error:
            raise GraphApiError("network_error", retryable=True) from error
        body: Any
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.is_success:
            return body if isinstance(body, dict) else {}
        error = body.get("error", {}) if isinstance(body, dict) else {}
        code = str(error.get("code") or f"http_{response.status_code}")
        retryable = (
            response.status_code == 429 or response.status_code >= 500 or code in _RETRYABLE_CODES
        )
        logger.warning(
            "graph_api_error",
            extra={"path": path.split("/")[-1], "status": response.status_code, "meta_code": code},
        )
        raise GraphApiError(code, retryable=retryable, http_status=response.status_code)

    def send_message(
        self, phone_number_id: str, token: str, to: str, body: Mapping[str, Any]
    ) -> str:
        result = self._request(
            "POST",
            f"/{phone_number_id}/messages",
            token,
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                **body,
            },
        )
        messages = result.get("messages") or []
        if not messages or not messages[0].get("id"):
            raise GraphApiError("missing_wamid", retryable=False)
        return str(messages[0]["id"])

    def mark_read(self, phone_number_id: str, token: str, wamid: str) -> None:
        self._request(
            "POST",
            f"/{phone_number_id}/messages",
            token,
            json={"messaging_product": "whatsapp", "status": "read", "message_id": wamid},
        )

    def phone_number(self, phone_number_id: str, token: str) -> PhoneNumberInfo:
        result = self._request(
            "GET",
            f"/{phone_number_id}",
            token,
            params={"fields": "display_phone_number,verified_name"},
        )
        return PhoneNumberInfo(
            display_phone_number=str(result.get("display_phone_number") or ""),
            verified_name=str(result.get("verified_name") or ""),
        )

    def subscribe_app(self, waba_id: str, token: str) -> None:
        self._request("POST", f"/{waba_id}/subscribed_apps", token)


class CloudApiSender:
    """Sends through the Cloud API with the connection's own (decrypted) token."""

    def __init__(self, client: GraphClient, cipher: TokenCipher) -> None:
        self._client = client
        self._cipher = cipher

    def send(self, connection: WhatsAppConnection, to: str, body: Mapping[str, Any]) -> str:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        return self._client.send_message(connection.phone_number_id, token, to, body)

    def send_template(
        self,
        connection: WhatsAppConnection,
        to: str,
        name: str,
        language: str,
        parameters: Sequence[str] = (),
    ) -> str:
        return self.send(connection, to, template_body(name, language, parameters))

    def mark_read(self, connection: WhatsAppConnection, wamid: str) -> None:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        self._client.mark_read(connection.phone_number_id, token, wamid)


class CloudGraphPort:
    """Connection checks against the real Graph API."""

    def __init__(self, client: GraphClient, cipher: TokenCipher) -> None:
        self._client = client
        self._cipher = cipher

    def phone_number(self, connection: WhatsAppConnection) -> PhoneInfo:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        info = self._client.phone_number(connection.phone_number_id, token)
        return PhoneInfo(info.display_phone_number, info.verified_name)

    def subscribe_app(self, connection: WhatsAppConnection) -> None:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        self._client.subscribe_app(connection.waba_id, token)


class LogGraphPort:
    """Log-sender connections (local development) never call Meta."""

    def phone_number(self, connection: WhatsAppConnection) -> PhoneInfo:
        return PhoneInfo(
            connection.display_phone_number or "+54 9 11 0000-0000",
            connection.verified_name or "Número de desarrollo",
        )

    def subscribe_app(self, connection: WhatsAppConnection) -> None:
        return None
