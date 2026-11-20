"""The agency's lead webhook (any CRM, Zapier, Make, ...): a signed JSON POST per lead
handed off to the team, and a test ping. The payload is documented in docs/integrations.md.

Headers:
- `X-Inmo24x7-Signature: sha256=<hex HMAC-SHA256 of the raw body with the secret>`;
- `X-Inmo24x7-Event: lead.handed_off` (or `ping` for "Enviar prueba");
- `X-Inmo24x7-Delivery: <uuid>`: the same on every retry of one delivery, so the receiver
  can drop duplicates.
"""

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from ..leads.domain.sinks import LeadSinkError, QualifiedLead, SinkResult

EVENT_HANDED_OFF = "lead.handed_off"
EVENT_PING = "ping"
SIGNATURE_HEADER = "X-Inmo24x7-Signature"
EVENT_HEADER = "X-Inmo24x7-Event"
DELIVERY_HEADER = "X-Inmo24x7-Delivery"
TIMEOUT_SECONDS = 10.0
MAX_URL_LENGTH = 500
SECRET_PREFIX = "whsec_"

UNREACHABLE = "webhook_unreachable"
REJECTED = "webhook_rejected"
SERVER_ERROR = "webhook_server_error"


def new_secret() -> str:
    return SECRET_PREFIX + secrets.token_urlsafe(32)


def sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def valid_url(url: str, *, allow_http: bool = False) -> bool:
    """https only (http only for local development, with a localhost host)."""
    if not url or len(url) > MAX_URL_LENGTH or any(char.isspace() for char in url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if not parts.hostname:
        return False
    if parts.scheme == "https":
        return True
    local = parts.hostname in ("localhost", "127.0.0.1") or parts.hostname.endswith(".local")
    return parts.scheme == "http" and allow_http and local


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def lead_payload(lead: QualifiedLead, delivery_id: UUID, event: str, sent_at: datetime) -> dict:
    return {
        "event": event,
        "delivery_id": str(delivery_id),
        "sent_at": sent_at.isoformat(),
        "lead": {
            "id": str(lead.id),
            "created_at": _iso(lead.created_at),
            "handed_off_at": _iso(lead.handed_off_at),
            "hand_off_reason": lead.hand_off_reason,
            "channel": lead.channel,
            "source": lead.source,
            "name": lead.name,
            "phone": lead.phone,
            "email": lead.email,
            "operation": lead.operation,
            "zone": lead.zone,
            "rooms": lead.rooms,
            "budget": dict(lead.budget) if lead.budget else None,
            "conditions": dict(lead.conditions),
            "properties": [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "address": item.address,
                    "operation": item.operation,
                    "price": item.price_label,
                    "link": item.link,
                    "source": item.source,
                    "external_id": item.external_id,
                    "external_ref": item.external_ref,
                }
                for item in lead.chosen
            ],
            "visit": {
                "starts_at": lead.visit.starts_at.isoformat(),
                "label": lead.visit.label,
                "property": lead.visit.property_label,
                "status": lead.visit.status,
            }
            if lead.visit
            else None,
            "summary": lead.summary,
            "do_not_contact": lead.do_not_contact,
            "panel_link": lead.panel_link,
        },
    }


def encode(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


class WebhookClient:
    """Posts signed bodies; the transport is injectable (tests use a fake receiver)."""

    def __init__(
        self, transport: httpx.BaseTransport | None = None, timeout: float = TIMEOUT_SECONDS
    ) -> None:
        self._http = httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def post(self, url: str, secret: str, event: str, delivery_id: UUID, body: bytes) -> SinkResult:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "inmo24x7-webhooks/1",
            SIGNATURE_HEADER: sign(secret, body),
            EVENT_HEADER: event,
            DELIVERY_HEADER: str(delivery_id),
        }
        try:
            response = self._http.post(url, content=body, headers=headers)
        except httpx.HTTPError as error:
            raise LeadSinkError(UNREACHABLE) from error
        status = response.status_code
        if 200 <= status < 300:
            return SinkResult(status)
        if status == 429 or status >= 500:
            raise LeadSinkError(SERVER_ERROR, status_code=status)
        # 3xx (redirects are not followed) and 4xx: the receiver said no; retrying the same
        # body will not change that.
        raise LeadSinkError(REJECTED, status_code=status, retry=False)


class WebhookLeadSink:
    def __init__(
        self,
        client: WebhookClient,
        url: str,
        secret: str,
        clock: Any,
    ) -> None:
        self._client = client
        self._url = url
        self._secret = secret
        self._clock = clock

    def deliver(self, lead: QualifiedLead, delivery_id: UUID, event: str) -> SinkResult:
        body = encode(lead_payload(lead, delivery_id, event, self._clock()))
        return self._client.post(self._url, self._secret, event, delivery_id, body)

    def ping(self, tenant_id: UUID, delivery_id: UUID, panel_url: str) -> SinkResult:
        body = encode(
            {
                "event": EVENT_PING,
                "delivery_id": str(delivery_id),
                "sent_at": self._clock().isoformat(),
                "tenant_id": str(tenant_id),
                "message": "Prueba de inmo24x7: si ves esto, el webhook funciona.",
                "panel_link": panel_url,
            }
        )
        return self._client.post(self._url, self._secret, EVENT_PING, delivery_id, body)
