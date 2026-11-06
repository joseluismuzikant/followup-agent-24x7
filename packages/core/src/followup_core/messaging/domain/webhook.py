"""The Cloud API webhook payload, parsed into what the pipeline needs. Pure functions."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .phones import canonical_wa_id

# Delivered by WhatsApp but not readable by the agent (it answers with a fixed text).
MEDIA_TYPES = frozenset(
    {"audio", "image", "video", "document", "sticker", "location", "contacts", "voice"}
)
IGNORED_TYPES = frozenset({"reaction", "system", "ephemeral", "unsupported", "request_welcome"})


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    wamid: str
    phone_number_id: str
    wa_id: str  # the sender, exactly as Meta wrote it; replies go here
    type: str  # "text", "button" (a reply button), or a media type
    sent_at: datetime
    text: str | None = None
    choice_id: str | None = None  # the id of the tapped reply button
    raw: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class StatusUpdate:
    wamid: str
    status: str  # sent | delivered | read | failed
    at: datetime
    error_code: str | None = None


def _timestamp(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _message(phone_number_id: str, item: Mapping[str, Any]) -> IncomingMessage | None:
    kind = str(item.get("type") or "")
    wamid, wa_id = item.get("id"), item.get("from")
    if not wamid or not wa_id or kind in IGNORED_TYPES:
        return None
    text: str | None = None
    choice: str | None = None
    if kind == "text":
        text = (item.get("text") or {}).get("body")
    elif kind == "interactive":
        reply = (item.get("interactive") or {}).get("button_reply") or (
            item.get("interactive") or {}
        ).get("list_reply")
        if not reply:
            return None
        kind, text, choice = "button", reply.get("title"), reply.get("id")
    elif kind == "button":  # a template's quick-reply button
        button = item.get("button") or {}
        text, choice = button.get("text"), button.get("payload")
    elif kind not in MEDIA_TYPES:
        kind = "unsupported"
    if kind in ("text", "button") and not (text or "").strip():
        return None
    return IncomingMessage(
        wamid=str(wamid),
        phone_number_id=phone_number_id,
        wa_id=canonical_wa_id(str(wa_id)),
        type=kind,
        sent_at=_timestamp(item.get("timestamp")),
        text=text,
        choice_id=choice,
        raw=item,
    )


def parse_webhook(
    payload: Mapping[str, Any],
) -> tuple[list[IncomingMessage], list[StatusUpdate]]:
    """Messages and delivery statuses from a `whatsapp_business_account` notification.
    Anything else (other fields, malformed entries) is skipped."""
    messages: list[IncomingMessage] = []
    statuses: list[StatusUpdate] = []
    for value in _values(payload):
        phone_number_id = str((value.get("metadata") or {}).get("phone_number_id") or "")
        if not phone_number_id:
            continue
        for item in value.get("messages") or []:
            if isinstance(item, Mapping) and (message := _message(phone_number_id, item)):
                messages.append(message)
        for item in value.get("statuses") or []:
            if not isinstance(item, Mapping) or not item.get("id") or not item.get("status"):
                continue
            errors = item.get("errors") or []
            code = errors[0].get("code") if errors and isinstance(errors[0], Mapping) else None
            statuses.append(
                StatusUpdate(
                    wamid=str(item["id"]),
                    status=str(item["status"]),
                    at=_timestamp(item.get("timestamp")),
                    error_code=str(code) if code is not None else None,
                )
            )
    return messages, statuses


@dataclass(frozen=True, slots=True)
class AccountUpdate:
    """An `account_update` event for one WABA (no personal data)."""

    waba_id: str
    event: str
    ban_state: str | None = None  # DISABLED_UPDATE: SCHEDULE_FOR_DISABLE | DISABLE | REINSTATE
    certification_status: str | None = None  # business verification: APPROVED | FAILED | ...


def parse_account_updates(payload: Mapping[str, Any]) -> list[AccountUpdate]:
    """`account_update` changes. For partner events `waba_info.waba_id` is the account; the
    entry id is the WABA otherwise."""
    updates: list[AccountUpdate] = []
    if payload.get("object") != "whatsapp_business_account":
        return updates
    for entry in payload.get("entry") or []:
        if not isinstance(entry, Mapping):
            continue
        for change in entry.get("changes") or []:
            if not isinstance(change, Mapping) or change.get("field") != "account_update":
                continue
            value = change.get("value")
            if not isinstance(value, Mapping) or not value.get("event"):
                continue
            waba_info = value.get("waba_info") or {}
            waba_id = str(waba_info.get("waba_id") or entry.get("id") or "")
            if not waba_id:
                continue
            ban = value.get("ban_info") or {}
            certification = value.get("partner_client_certification_info") or {}
            updates.append(
                AccountUpdate(
                    waba_id=waba_id,
                    event=str(value["event"]),
                    ban_state=str(ban["waba_ban_state"]) if ban.get("waba_ban_state") else None,
                    certification_status=(
                        str(certification["status"]) if certification.get("status") else None
                    ),
                )
            )
    return updates


def _values(payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    if payload.get("object") != "whatsapp_business_account":
        return
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            if (change or {}).get("field") == "messages" and isinstance(
                change.get("value"), Mapping
            ):
                yield change["value"]
