"""What we send to WhatsApp and how its delivery is tracked."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from followup_core.conversation.domain.thread import Message

from .connection import WhatsAppConnection

MAX_TEXT_LENGTH = 4096
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
SERVICE_WINDOW = timedelta(hours=24)
OUTSIDE_SERVICE_WINDOW = "outside_service_window"
UNREADABLE_REPLY = "Por ahora solo puedo leer mensajes de texto. ¿Me lo escribís?"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    # The connection is in error (token revoked, ...): sent once the customer reconnects.
    WAITING = "waiting_connection"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


# A status only moves forward (Meta may deliver "read" before "delivered").
_RANK = {
    DeliveryStatus.QUEUED: 0,
    DeliveryStatus.WAITING: 0,
    DeliveryStatus.SENT: 1,
    DeliveryStatus.DELIVERED: 2,
    DeliveryStatus.READ: 3,
    DeliveryStatus.FAILED: 4,
}


def advances(current: DeliveryStatus, new: DeliveryStatus) -> bool:
    return _RANK[new] > _RANK[current]


def overall_status(parts: Sequence[DeliveryStatus]) -> DeliveryStatus | None:
    """One label for a message sent as several WhatsApp messages: failed if any failed,
    otherwise the least advanced part."""
    if not parts:
        return None
    if DeliveryStatus.FAILED in parts:
        return DeliveryStatus.FAILED
    return min(parts, key=lambda status: _RANK[status])


@dataclass(frozen=True, slots=True)
class OutboundPart:
    id: UUID
    message_id: UUID
    part: int
    wa_id: str
    body: Mapping[str, Any]  # the Cloud API request body without "to"/"messaging_product"
    status: DeliveryStatus
    wamid: str | None = None
    error_code: str | None = None


def text_bodies(text: str) -> list[dict[str, Any]]:
    """A text message, split into chunks WhatsApp accepts (on line breaks when possible)."""
    chunks: list[str] = []
    rest = text.strip()
    while len(rest) > MAX_TEXT_LENGTH:
        cut = rest.rfind("\n", 0, MAX_TEXT_LENGTH)
        cut = cut if cut > MAX_TEXT_LENGTH // 2 else MAX_TEXT_LENGTH
        chunks.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        chunks.append(rest)
    return [{"type": "text", "text": {"body": chunk, "preview_url": False}} for chunk in chunks]


def buttons_body(text: str, buttons: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Reply buttons: (id, title) pairs, at most 3, titles cut to 20 characters."""
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text[:1024]},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {"id": choice_id[:256], "title": title[:MAX_BUTTON_TITLE]},
                    }
                    for choice_id, title in buttons[:MAX_BUTTONS]
                ]
            },
        },
    }


class MessageRenderer(Protocol):
    """Turns a stored agent message into Cloud API bodies. The product renders its own
    payloads (property cards, visit slots); system messages render to nothing."""

    def __call__(self, message: Message) -> list[dict[str, Any]]: ...


class SendError(Exception):
    def __init__(self, code: str, *, retryable: bool, http_status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.http_status = http_status


class WhatsAppSender(Protocol):
    def send(self, connection: WhatsAppConnection, to: str, body: Mapping[str, Any]) -> str:
        """Sends one message; returns its wamid. Raises SendError."""
        ...

    def send_template(
        self,
        connection: WhatsAppConnection,
        to: str,
        name: str,
        language: str,
        parameters: Sequence[str] = (),
    ) -> str:
        """For messages outside the 24-hour window. Raises SendError."""
        ...

    def mark_read(self, connection: WhatsAppConnection, wamid: str) -> None: ...


def within_service_window(last_inbound_at: datetime | None, now: datetime) -> bool:
    return last_inbound_at is not None and now - last_inbound_at < SERVICE_WINDOW


def template_body(name: str, language: str, parameters: Sequence[str]) -> dict[str, Any]:
    """A Cloud API template message body: the only kind allowed outside the 24-hour window."""
    template: dict[str, Any] = {"name": name, "language": {"code": language}}
    if parameters:
        template["components"] = [
            {
                "type": "body",
                "parameters": [{"type": "text", "text": value} for value in parameters],
            }
        ]
    return {"type": "template", "template": template}
