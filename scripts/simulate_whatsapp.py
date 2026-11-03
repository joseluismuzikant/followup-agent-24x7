"""Send a WhatsApp message to the local API as Meta would: a real-shaped Cloud API webhook,
signed with META_APP_SECRET. No Meta account needed.

    uv run --all-packages python scripts/simulate_whatsapp.py "Hola, busco un 2 amb en Palermo"
    uv run --all-packages python scripts/simulate_whatsapp.py --slot <slot id> "jue 4/11 10:30"
    uv run --all-packages python scripts/simulate_whatsapp.py --audio

The slot ids are in the API log and in Consultas (each button's id).

The seed connects "Inmobiliaria Sur" to the fake number dev-phone-1 with the log sender, so
the agent's answers show in the API log, in Consultas and in Mailpit (new-lead email).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any
from uuid import uuid4

from _cli import ROOT, load_env_file

DEFAULT_FROM = "5491155550188"
DEFAULT_PHONE_NUMBER_ID = "dev-phone-1"
DEFAULT_API = "http://localhost:8001"


def message_payload(
    text: str | None,
    *,
    sender: str = DEFAULT_FROM,
    phone_number_id: str = DEFAULT_PHONE_NUMBER_ID,
    slot: str | None = None,
    audio: bool = False,
    name: str = "Visitante de prueba",
    wamid: str | None = None,
    timestamp: int | None = None,
) -> dict[str, Any]:
    """A `messages` notification as the Cloud API sends it (text, reply button or audio)."""
    message: dict[str, Any] = {
        "from": sender,
        "id": wamid or f"wamid.sim.{uuid4().hex}",
        "timestamp": str(timestamp or int(time.time())),
    }
    if audio:
        message |= {
            "type": "audio",
            "audio": {"id": uuid4().hex, "mime_type": "audio/ogg; codecs=opus", "voice": True},
        }
    elif slot:
        message |= {
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": slot, "title": text or slot},
            },
        }
    else:
        message |= {"type": "text", "text": {"body": text or ""}}
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "dev-waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5491155550100",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": name}, "wa_id": sender}],
                            "messages": [message],
                        },
                    }
                ],
            }
        ],
    }


def status_payload(
    wamid: str,
    status: str,
    *,
    phone_number_id: str = DEFAULT_PHONE_NUMBER_ID,
    recipient: str = DEFAULT_FROM,
    error_code: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": wamid,
        "status": status,
        "timestamp": str(int(time.time())),
        "recipient_id": recipient,
    }
    if error_code is not None:
        item["errors"] = [{"code": error_code, "title": "error"}]
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "dev-waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": phone_number_id},
                            "statuses": [item],
                        },
                    }
                ],
            }
        ],
    }


def sign(body: bytes, secret: str) -> str:
    """The X-Hub-Signature-256 header Meta computes over the raw body."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post a signed WhatsApp webhook to the API.")
    parser.add_argument("text", nargs="?", default=None, help="the message text")
    parser.add_argument("--from", dest="sender", default=DEFAULT_FROM, help="the sender's wa_id")
    parser.add_argument("--phone-number-id", default=DEFAULT_PHONE_NUMBER_ID)
    parser.add_argument("--slot", help="send a reply-button tap with this slot id")
    parser.add_argument("--audio", action="store_true", help="send a voice note")
    parser.add_argument("--api", default=os.getenv("SIMULATE_API_URL", DEFAULT_API))
    args = parser.parse_args(argv)
    if not args.text and not args.audio:
        parser.error("write a message, or use --audio")

    load_env_file(ROOT / ".env")
    secret = os.getenv("META_APP_SECRET") or "dev-app-secret"
    body = encode(
        message_payload(
            args.text,
            sender=args.sender,
            phone_number_id=args.phone_number_id,
            slot=args.slot,
            audio=args.audio,
        )
    )
    request = urllib.request.Request(
        f"{args.api.rstrip('/')}/webhooks/whatsapp",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign(body, secret)},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f"{response.status} {response.read().decode()}")
    except urllib.error.HTTPError as error:
        print(f"{error.code} {error.read().decode()}", file=sys.stderr)
        return 1
    except urllib.error.URLError as error:
        print(
            f"No se pudo conectar con la API ({error.reason}). ¿Está corriendo dev.py?",
            file=sys.stderr,
        )
        return 1
    print("El agente responde en unos segundos: mirá el log del worker, Consultas y Mailpit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
