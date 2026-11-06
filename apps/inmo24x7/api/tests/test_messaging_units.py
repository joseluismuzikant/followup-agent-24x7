"""Messaging pieces without the database: encryption, phones, parsing, statuses, rendering and
the job registry."""

import base64
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from followup_core.conversation.domain.thread import Author, Direction, Message
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.messaging.domain.outbound import (
    DeliveryStatus,
    advances,
    overall_status,
    within_service_window,
)
from followup_core.messaging.domain.phones import (
    canonical_wa_id,
    display,
    to_cloud_api_recipient,
    to_e164,
)
from followup_core.messaging.domain.webhook import parse_webhook
from followup_core.messaging.infrastructure.crypto import TokenCipher, TokenCipherError
from inmo24x7_api.container import job_handlers
from inmo24x7_api.leads.whatsapp import LeadMessageRenderer
from whatsapp_fakes import FakeGraph, build_services, simulate_whatsapp

KEY = base64.b64encode(b"0" * 32).decode()
OTHER_KEY = base64.b64encode(b"1" * 32).decode()
ROOT = Path(__file__).resolve().parents[4]


# --- Token encryption -----------------------------------------------------------------------


def test_tokens_round_trip_with_a_key_id_prefix_and_random_nonces() -> None:
    cipher = TokenCipher.from_setting(KEY)

    first, second = cipher.encrypt("EAAG-token"), cipher.encrypt("EAAG-token")

    assert first.startswith("k1:") and "EAAG" not in first
    assert first != second
    assert cipher.decrypt(first) == cipher.decrypt(second) == "EAAG-token"


def test_a_wrong_or_unknown_key_cannot_decrypt() -> None:
    stored = TokenCipher.from_setting(KEY).encrypt("EAAG-token")

    with pytest.raises(TokenCipherError):
        TokenCipher.from_setting(OTHER_KEY).decrypt(stored)
    with pytest.raises(TokenCipherError):
        TokenCipher.from_setting(KEY, key_id="k2").decrypt(stored)
    with pytest.raises(TokenCipherError):
        TokenCipher.from_setting(KEY).decrypt("k1:not-base64!!")


def test_rotation_keeps_old_tokens_readable() -> None:
    old = TokenCipher.from_setting(KEY).encrypt("EAAG-token")
    rotated = TokenCipher(
        {"k1": base64.b64decode(KEY), "k2": base64.b64decode(OTHER_KEY)}, current="k2"
    )

    assert rotated.decrypt(old) == "EAAG-token"
    assert rotated.encrypt("x").startswith("k2:")


@pytest.mark.parametrize("key", ["c2hvcnQ=", "not base64", ""])
def test_keys_must_be_32_bytes_of_base64(key: str) -> None:
    with pytest.raises(TokenCipherError):
        TokenCipher.from_setting(key)


# --- Phones ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "number",
    [
        "11 5555-0188",
        "011 15 5555-0188",
        "15 5555 0188",
        "+54 9 11 5555 0188",
        "+54 11 5555 0188",
        "5491155550188",
        "541155550188",
        "(011) 5555-0188",
    ],
)
def test_argentine_formats_normalize_to_one_e164(number: str) -> None:
    assert to_e164(number) == "+5491155550188"
    assert display("+5491155550188") == "+54 9 11 5555-0188"


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        ("0341 15 456-7890", "+5493414567890"),
        ("+54 9 351 456 7890", "+5493514567890"),
        ("+1 415 555 2671", "+14155552671"),
        ("5555-0188", None),
        ("123", None),
        ("", None),
    ],
)
def test_other_numbers(number: str, expected: str | None) -> None:
    assert to_e164(number) == expected


@pytest.mark.parametrize(
    ("e164", "recipient"),
    [
        ("+5491151060793", "541151060793"),
        ("+5493415551234", "543415551234"),  # Rosario
        ("+541151060793", "541151060793"),  # landline-style, no 9
        ("+14155550100", "14155550100"),
        ("+525512345678", "525512345678"),  # Mexico
        ("5491151060793", "541151060793"),  # a wa_id, already without "+"
    ],
)
def test_the_cloud_api_recipient_drops_the_argentine_mobile_9(e164: str, recipient: str) -> None:
    assert to_cloud_api_recipient(e164) == recipient


@pytest.mark.parametrize(
    ("wa_id", "expected"),
    [
        ("541151060793", "5491151060793"),
        ("5491151060793", "5491151060793"),
        ("14155550100", "14155550100"),
        ("5215512345678", "5215512345678"),
    ],
)
def test_inbound_wa_ids_keep_the_argentine_mobile_9(wa_id: str, expected: str) -> None:
    assert canonical_wa_id(wa_id) == expected


def test_the_graph_client_sends_argentine_mobiles_without_the_9() -> None:
    graph = FakeGraph()
    client = build_services(graph).graph

    client.send_message(
        "pn-1", "token", "+5491151060793", {"type": "text", "text": {"body": "Hola"}}
    )

    (body,) = graph.sent()
    assert body["to"] == "541151060793"


# --- Webhook parsing ------------------------------------------------------------------------


def test_text_button_and_audio_messages_are_parsed() -> None:
    text = simulate_whatsapp.message_payload("Hola", wamid="w1", timestamp=1_793_000_000)
    button = simulate_whatsapp.message_payload("jue 6/11 10:30", slot="slot-1", wamid="w2")
    audio = simulate_whatsapp.message_payload(None, audio=True, wamid="w3")

    ((hola,), _) = parse_webhook(text)
    ((tap,), _) = parse_webhook(button)
    ((voice,), _) = parse_webhook(audio)

    assert (hola.type, hola.text, hola.wa_id, hola.phone_number_id) == (
        "text",
        "Hola",
        "5491155550188",
        "dev-phone-1",
    )
    assert hola.sent_at == datetime.fromtimestamp(1_793_000_000, UTC)
    assert (tap.type, tap.text, tap.choice_id) == ("button", "jue 6/11 10:30", "slot-1")
    assert (voice.type, voice.text) == ("audio", None)


def test_reactions_and_other_fields_are_ignored() -> None:
    payload = simulate_whatsapp.message_payload("x")
    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    message.update({"type": "reaction", "reaction": {"emoji": "👍"}})
    other_field = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "x"}]}]}

    assert parse_webhook(payload) == ([], [])
    assert parse_webhook(other_field) == ([], [])
    assert parse_webhook({"object": "page"}) == ([], [])


def test_status_updates_carry_meta_error_codes() -> None:
    payload = simulate_whatsapp.status_payload("wamid.1", "failed", error_code=131026)

    (_, (status,)) = parse_webhook(payload)

    assert (status.wamid, status.status, status.error_code) == ("wamid.1", "failed", "131026")


# --- Delivery statuses ------------------------------------------------------------------------


def test_statuses_only_move_forward_and_failed_wins() -> None:
    assert advances(DeliveryStatus.SENT, DeliveryStatus.READ)
    assert not advances(DeliveryStatus.READ, DeliveryStatus.DELIVERED)
    assert (
        overall_status([DeliveryStatus.READ, DeliveryStatus.DELIVERED]) is DeliveryStatus.DELIVERED
    )
    assert overall_status([DeliveryStatus.READ, DeliveryStatus.FAILED]) is DeliveryStatus.FAILED
    assert overall_status([]) is None


def test_the_service_window_is_24_hours() -> None:
    now = datetime(2026, 11, 3, 12, tzinfo=UTC)

    assert within_service_window(datetime(2026, 11, 2, 12, 1, tzinfo=UTC), now)
    assert not within_service_window(datetime(2026, 11, 2, 12, 0, tzinfo=UTC), now)
    assert not within_service_window(None, now)


# --- Rendering --------------------------------------------------------------------------------


def _message(payload: dict | None, author: Author = Author.AGENT, text: str = "Mirá") -> Message:
    return Message(uuid4(), uuid4(), Direction.OUTBOUND, author, text, datetime.now(UTC), payload)


def test_cards_become_one_text_each_with_the_listing_link() -> None:
    card = {
        "id": "p1",
        "title": "2 ambientes",
        "address": "Gorriti 4800",
        "price_label": "$850.000 por mes",
        "link": "https://inmo.example/p/1",
        "over_budget": True,
        "is_sample": False,
    }
    sample = {**card, "link": "/ejemplo/a", "is_sample": True, "over_budget": False}

    bodies = LeadMessageRenderer("https://panel.example")(_message({"cards": [card, sample]}))

    assert [body["text"]["body"] for body in bodies] == [
        "Mirá",
        "*2 ambientes*\nGorriti 4800\n$850.000 por mes\nUn poco más de tu presupuesto\n"
        "https://inmo.example/p/1",
        "*2 ambientes*\nGorriti 4800\n$850.000 por mes\nhttps://panel.example/ejemplo/a",
    ]
    assert [body["text"]["preview_url"] for body in bodies] == [False, True, True]


def test_slots_become_at_most_three_short_reply_buttons() -> None:
    slots = [
        {"id": f"slot-{n}", "label": "miércoles 12/11, 10:30", "short_label": "mié 12/11 10:30"}
        for n in range(4)
    ]

    (body,) = LeadMessageRenderer("https://panel.example")(_message({"slots": slots}))

    buttons = body["interactive"]["action"]["buttons"]
    assert body["type"] == "interactive" and body["interactive"]["type"] == "button"
    assert [b["reply"] for b in buttons] == [
        {"id": f"slot-{n}", "title": "mié 12/11 10:30"} for n in range(3)
    ]


def test_system_messages_are_never_sent() -> None:
    renderer = LeadMessageRenderer("https://panel.example")

    assert renderer(_message(None, Author.SYSTEM, "El agente derivó la consulta")) == []


# --- Job registry -------------------------------------------------------------------------------


def test_every_enqueued_job_kind_has_exactly_one_handler(db_session) -> None:
    handlers = job_handlers(db_session, build_services(FakeGraph()), FakeLanguageModel())

    # Every NewJob(...) in the code names its kind with a constant; collect their values.
    sources = [
        *ROOT.joinpath("packages/core/src").rglob("*.py"),
        *ROOT.joinpath("apps/inmo24x7/api/src").rglob("*.py"),
    ]
    text = "\n".join(path.read_text("utf-8") for path in sources)
    constants = dict(re.findall(r'^(\w+_JOB) = "([\w.]+)"', text, re.MULTILINE))
    enqueued = set(re.findall(r"NewJob\(\s*(\w+_JOB)", text))

    assert enqueued and enqueued <= set(constants)
    assert {constants[name] for name in enqueued} <= handlers.kinds
    assert handlers.kinds == set(constants.values())
