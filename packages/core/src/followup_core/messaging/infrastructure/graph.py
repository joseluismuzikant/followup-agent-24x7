"""The Meta Graph API (WhatsApp Cloud API) over httpx. Tests mock it at the HTTP level with
httpx.MockTransport; nothing here logs a token, a phone number or message text."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from ..application.connections import PhoneInfo
from ..domain.connection import BusinessVerification, WhatsAppConnection
from ..domain.outbound import SendError, template_body
from ..domain.phones import to_cloud_api_recipient
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
    quality_rating: str | None = None
    name_status: str | None = None


_PHONE_FIELDS = "display_phone_number,verified_name,quality_rating,name_status"
# Business node `verification_status` (Meta's values, lowercase).
_VERIFICATION = {
    "verified": BusinessVerification.VERIFIED,
    "not_verified": BusinessVerification.PENDING,
    "pending": BusinessVerification.PENDING,
    "pending_submission": BusinessVerification.PENDING,
    "pending_need_more_info": BusinessVerification.PENDING,
    "failed": BusinessVerification.FAILED,
    "rejected": BusinessVerification.FAILED,
    "revoked": BusinessVerification.FAILED,
}


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
        self,
        method: str,
        path: str,
        token: str | None,
        json: Mapping[str, Any] | None = None,
        **kw: Any,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = self._client.request(method, path, json=json, headers=headers, **kw)
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
                "to": to_cloud_api_recipient(to),
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
            "GET", f"/{phone_number_id}", token, params={"fields": _PHONE_FIELDS}
        )
        return PhoneNumberInfo(
            display_phone_number=str(result.get("display_phone_number") or ""),
            verified_name=str(result.get("verified_name") or ""),
            quality_rating=str(result["quality_rating"]) if result.get("quality_rating") else None,
            name_status=str(result["name_status"]) if result.get("name_status") else None,
        )

    def subscribe_app(self, waba_id: str, token: str) -> None:
        self._request("POST", f"/{waba_id}/subscribed_apps", token)

    def exchange_code(self, app_id: str, app_secret: str, code: str) -> str:
        """Embedded Signup: the 30-second code for the customer's business token."""
        result = self._request(
            "GET",
            "/oauth/access_token",
            None,
            params={"client_id": app_id, "client_secret": app_secret, "code": code},
        )
        token = result.get("access_token")
        if not token:
            raise GraphApiError("missing_token", retryable=False)
        return str(token)

    def register(self, phone_number_id: str, token: str, pin: str) -> None:
        self._request(
            "POST",
            f"/{phone_number_id}/register",
            token,
            json={"messaging_product": "whatsapp", "pin": pin},
        )

    def create_message_template(
        self, waba_id: str, token: str, template: Mapping[str, Any]
    ) -> tuple[str, str]:
        """Submits a template for review in the business's WABA: (Meta's id, its status)."""
        result = self._request("POST", f"/{waba_id}/message_templates", token, json=template)
        template_id = result.get("id")
        if not template_id:
            raise GraphApiError("missing_template_id", retryable=False)
        return str(template_id), str(result.get("status") or "PENDING")

    def message_templates(self, waba_id: str, token: str) -> list[dict[str, Any]]:
        """The WABA's templates (id, name, language, status, rejected reason), every page."""
        items: list[dict[str, Any]] = []
        params: dict[str, Any] = {
            "fields": "id,name,language,status,category,rejected_reason",
            "limit": 100,
        }
        for _ in range(20):  # 2,000 templates is far more than a business has
            result = self._request("GET", f"/{waba_id}/message_templates", token, params=params)
            items.extend(item for item in result.get("data") or [] if isinstance(item, dict))
            after = ((result.get("paging") or {}).get("cursors") or {}).get("after")
            if not after or not (result.get("paging") or {}).get("next"):
                break
            params = {**params, "after": after}
        return items

    def business_verification(self, business_id: str, token: str) -> BusinessVerification:
        """Not documented for business tokens everywhere: any failure is UNKNOWN."""
        try:
            result = self._request(
                "GET", f"/{business_id}", token, params={"fields": "verification_status"}
            )
        except GraphApiError:
            return BusinessVerification.UNKNOWN
        status = str(result.get("verification_status") or "").lower()
        return _VERIFICATION.get(status, BusinessVerification.UNKNOWN)


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
        return PhoneInfo(
            info.display_phone_number, info.verified_name, info.quality_rating, info.name_status
        )

    def subscribe_app(self, connection: WhatsAppConnection) -> None:
        token = self._cipher.decrypt(connection.access_token_encrypted)
        self._client.subscribe_app(connection.waba_id, token)

    def business_verification(self, connection: WhatsAppConnection) -> BusinessVerification:
        if not connection.business_id:
            return BusinessVerification.UNKNOWN
        token = self._cipher.decrypt(connection.access_token_encrypted)
        return self._client.business_verification(connection.business_id, token)


class LogGraphPort:
    """Log-sender connections (local development) never call Meta."""

    def phone_number(self, connection: WhatsAppConnection) -> PhoneInfo:
        return PhoneInfo(
            connection.display_phone_number or "+54 9 11 0000-0000",
            connection.verified_name or "Número de desarrollo",
        )

    def subscribe_app(self, connection: WhatsAppConnection) -> None:
        return None

    def business_verification(self, connection: WhatsAppConnection) -> BusinessVerification:
        return connection.business_verification


class CloudSignupGraph:
    """Embedded Signup's Graph calls: the app's id and secret exchange the code, then the
    customer's business token does the rest."""

    def __init__(self, client: GraphClient, app_id: str, app_secret: str) -> None:
        self._client = client
        self._app_id = app_id
        self._app_secret = app_secret

    def exchange_code(self, code: str) -> str:
        if not self._app_id:
            raise GraphApiError("embedded_signup_not_configured", retryable=False)
        return self._client.exchange_code(self._app_id, self._app_secret, code)

    def subscribe_app(self, waba_id: str, token: str) -> None:
        self._client.subscribe_app(waba_id, token)

    def register(self, phone_number_id: str, token: str, pin: str) -> None:
        self._client.register(phone_number_id, token, pin)

    def phone_number(self, phone_number_id: str, token: str) -> PhoneInfo:
        info = self._client.phone_number(phone_number_id, token)
        return PhoneInfo(
            info.display_phone_number, info.verified_name, info.quality_rating, info.name_status
        )

    def business_verification(self, business_id: str, token: str) -> BusinessVerification:
        return self._client.business_verification(business_id, token)
