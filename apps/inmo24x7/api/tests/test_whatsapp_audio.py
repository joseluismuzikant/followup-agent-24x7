"""Voice notes on WhatsApp (TRANSCRIBE_MODEL): downloaded from Meta, transcribed, answered
like text. The real pipeline and database; Meta and the transcriber are fakes."""

import struct
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.domain.transcription import (
    Transcript,
    TranscriptionError,
    TranscriptionFailure,
)
from followup_core.conversation.infrastructure.transcribers import FakeTranscriber
from followup_core.conversation.infrastructure.usage import SqlAlchemyLlmUsageRecorder
from followup_core.messaging.domain.opt_out import OPT_OUT_CONFIRMATION
from followup_core.messaging.domain.outbound import UNHEARD_AUDIO_REPLY, UNREADABLE_REPLY
from followup_platform.billing.prices import load_prices
from inmo24x7_api.container import get_messaging_services
from inmo24x7_api.main import app
from inmo24x7_api.privacy.erasure import SqlAlchemyErasure
from test_setup_endpoints import Account, _body
from whatsapp_fakes import VISITOR, FakeGraph, WhatsAppWorld, build_services, connect, make_sessions


def ogg_opus(seconds: float, text: bytes = b"") -> bytes:
    """A minimal Ogg Opus shape: OpusHead with a 312-sample pre-skip, and a last page whose
    granule position says the length (48 kHz)."""
    head = b"OggS" + bytes(22) + b"OpusHead" + b"\x01\x01" + struct.pack("<H", 312) + bytes(8)
    last = b"OggS\x00\x04" + struct.pack("<q", int(seconds * 48_000) + 312) + bytes(16)
    return head + text + last


class FlakyTranscriber(FakeTranscriber):
    """Fails with a retryable error `failures` times, then works."""

    def __init__(self, failures: int, model: str = "fake") -> None:
        super().__init__(model=model)
        self.failures = failures

    def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        if self.failures > 0:
            self.calls += 1
            self.failures -= 1
            raise TranscriptionError(TranscriptionFailure.PROVIDER_ERROR, retryable=True)
        return super().transcribe(audio, mime_type)


class PricedTranscriber(FakeTranscriber):
    """The fake, recorded as OpenAI's model so the price file prices it."""

    @property
    def model_name(self) -> str:
        return "openai:gpt-transcribe"


def _world(client, auth, database, transcriber=None, usage: bool = False) -> WhatsAppWorld:
    graph = FakeGraph()
    services = build_services(graph, transcriber=transcriber)
    app.dependency_overrides[get_messaging_services] = lambda: services
    sessions = make_sessions(database)
    recorder = SqlAlchemyLlmUsageRecorder(sessions, load_prices()) if usage else None
    world = WhatsAppWorld(client, sessions, services, graph, usage=recorder)
    owner = Account(client, auth)
    setup = owner.get("/agent-setup").json()
    always = [{"weekday": day, "opens": "00:00", "closes": "23:30"} for day in range(7)]
    owner.put("/agent-setup", _body(setup, business_hours=always))
    admin = Account(client, auth, "Plataforma")
    auth.make_admin(admin.user_id)
    assert connect(client, admin.headers, owner.tenant_id, sender="cloud").status_code == 200
    world.owner = owner  # type: ignore[attr-defined]
    return world


@pytest.fixture
def make_world(client: TestClient, auth, database):
    yield lambda **kwargs: _world(client, auth, database, **kwargs)
    app.dependency_overrides.pop(get_messaging_services, None)


def _texts(world: WhatsAppWorld) -> list[str]:
    return [body["text"]["body"] for body in world.graph.sent() if body["type"] == "text"]


def _agent_turns(world: WhatsAppWorld) -> list[tuple[str, str, str]]:
    return [row for row in world.transcript() if row[1] == "agent"]


def test_a_voice_note_is_transcribed_and_answered_like_text(make_world) -> None:
    transcriber = FakeTranscriber()
    world = make_world(transcriber=transcriber)
    world.graph.audio = b"Hola, quiero alquilar en Palermo"

    assert world.say(None, audio=True) == 200
    world.run()

    assert transcriber.calls == 1
    (inbound, *replies) = world.transcript()
    assert inbound == ("inbound", "visitor", "Hola, quiero alquilar en Palermo")
    assert replies and all(author == "agent" for _, author, _ in replies)
    sent = _texts(world)
    assert UNHEARD_AUDIO_REPLY not in sent and UNREADABLE_REPLY not in sent
    # Stored as an audio with its transcript; the audio itself is nowhere.
    (row,) = world.sql(
        "SELECT content_type, text FROM conversation_messages WHERE direction = 'inbound'"
    )
    assert (row.content_type, row.text) == ("audio", "Hola, quiero alquilar en Palermo")
    # Meta's media URL and the token are never logged or stored.
    (event,) = world.sql("SELECT text, payload::text AS payload FROM whatsapp_inbound_events")
    assert event.text == "Hola, quiero alquilar en Palermo"
    assert "lookaside" not in event.payload


def test_a_voice_note_and_a_text_in_one_burst_are_one_turn(make_world) -> None:
    world = make_world(transcriber=FakeTranscriber())
    world.graph.audio = b"Hola, busco un 2 ambientes"

    world.say(None, audio=True)
    world.say("en Palermo")
    world.run()

    rows = world.transcript()
    assert [row[:2] for row in rows[:2]] == [("inbound", "visitor"), ("inbound", "visitor")]
    assert rows[0][2] == "Hola, busco un 2 ambientes"
    # One answer after both: no agent line between the two inbound messages.
    assert all(author == "agent" for _, author, _ in rows[2:])
    assert len(world.sql("SELECT 1 FROM conversation_threads WHERE channel = 'whatsapp'")) == 1


def test_a_voice_note_over_the_limit_gets_the_fixed_reply_without_transcribing(
    make_world,
) -> None:
    transcriber = FakeTranscriber()
    world = make_world(transcriber=transcriber)
    world.graph.audio = ogg_opus(130)

    world.say(None, audio=True)
    world.run()

    assert transcriber.calls == 0
    assert _texts(world) == [UNHEARD_AUDIO_REPLY]
    (row,) = world.sql("SELECT text FROM conversation_messages WHERE direction = 'inbound'")
    assert row.text == ""


def test_a_file_over_the_size_cap_is_never_downloaded(make_world) -> None:
    transcriber = FakeTranscriber()
    world = make_world(transcriber=transcriber)
    world.graph.audio_size = 50 * 1024 * 1024

    world.say(None, audio=True)
    world.run()

    assert transcriber.calls == 0
    assert _texts(world) == [UNHEARD_AUDIO_REPLY]
    assert not [path for _, path, _ in world.graph.requests if "attachments" in path]


def test_a_failed_transcription_gets_the_fixed_reply(make_world) -> None:
    failure = TranscriptionError(TranscriptionFailure.UNSUPPORTED)
    world = make_world(transcriber=FakeTranscriber(fail_with=failure))

    world.say(None, audio=True)
    world.run()

    assert _texts(world) == [UNHEARD_AUDIO_REPLY]
    assert world.jobs("whatsapp.process") == [("done", 1)]


def test_a_retryable_error_goes_through_the_backoff_then_answers(make_world) -> None:
    transcriber = FlakyTranscriber(failures=1)
    world = make_world(transcriber=transcriber)
    world.graph.audio = b"Hola, quiero alquilar en Palermo"

    world.say(None, audio=True)
    world.run()
    assert _texts(world) == []  # waiting for the retry (a failed attempt, due again later)
    assert world.jobs("whatsapp.process") == [("failed", 1)]

    world.run(after_seconds=60)

    assert transcriber.calls == 2
    assert world.transcript()[0][2] == "Hola, quiero alquilar en Palermo"
    assert UNHEARD_AUDIO_REPLY not in _texts(world)


def test_a_provider_that_keeps_failing_ends_in_the_fixed_reply(make_world) -> None:
    transcriber = FlakyTranscriber(failures=10)
    world = make_world(transcriber=transcriber)

    world.say(None, audio=True)
    for _ in range(5):
        world.run(after_seconds=120)

    assert transcriber.calls == 3  # never the job's full budget: a lead is waiting
    assert _texts(world) == [UNHEARD_AUDIO_REPLY]


def test_baja_said_in_a_voice_note_opts_out(make_world) -> None:
    world = make_world(transcriber=FakeTranscriber())
    world.graph.audio = b"BAJA"

    world.say(None, audio=True)
    world.run()

    assert _texts(world) == [OPT_OUT_CONFIRMATION]
    assert world.sql("SELECT wa_id FROM do_not_contact")


def test_without_transcribe_model_a_voice_note_gets_todays_reply(make_world) -> None:
    world = make_world()

    world.say(None, audio=True)
    world.run()

    assert _texts(world) == [UNREADABLE_REPLY]
    assert not [path for _, path, _ in world.graph.requests if "media-" in path]


def test_images_keep_the_fixed_reply_even_with_transcription_on(make_world) -> None:
    transcriber = FakeTranscriber()
    world = make_world(transcriber=transcriber)
    payload = world.post  # the image notification, built from a text one
    import simulate_whatsapp

    notification = simulate_whatsapp.message_payload(
        "x", sender=VISITOR, phone_number_id="pn-test-1"
    )
    message = notification["entry"][0]["changes"][0]["value"]["messages"][0]
    message.pop("text")
    message.update({"type": "image", "image": {"id": "media-img", "mime_type": "image/jpeg"}})
    assert payload(notification) == 200
    world.run()

    assert transcriber.calls == 0
    assert _texts(world) == [UNREADABLE_REPLY]


def test_each_transcription_is_a_priced_usage_row(make_world) -> None:
    world = make_world(transcriber=PricedTranscriber(), usage=True)
    world.graph.audio = ogg_opus(30, b"Hola")

    world.say(None, audio=True)
    world.run()

    (row,) = world.sql(
        "SELECT provider, model, audio_seconds, cost_usd, input_tokens, thread_id "
        "FROM llm_usage WHERE operation = 'transcribe'"
    )
    assert (row.provider, row.model) == ("openai", "openai:gpt-transcribe")
    assert row.audio_seconds == pytest.approx(30)
    # USD 0.27 per hour, by the second: 30 s = 0.00225.
    assert row.cost_usd == Decimal("0.002250")
    assert row.input_tokens == 0 and row.thread_id is None


def test_deleting_the_contact_takes_the_transcripts_with_it(make_world) -> None:
    world = make_world(transcriber=FakeTranscriber())
    world.graph.audio = b"Hola, mi nombre es Ana y busco en Palermo"
    world.say(None, audio=True)
    world.run()
    tenant_id = world.owner.tenant_id  # type: ignore[attr-defined]

    with world.sessions() as session:
        SqlAlchemyErasure(session).delete_contact(tenant_id, VISITOR)
        session.commit()

    for table in ("conversation_messages", "whatsapp_inbound_events"):
        rows = world.sql(f"SELECT 1 FROM {table} WHERE text LIKE '%Ana%'")  # noqa: S608
        assert rows == [], table
