"""The transcription adapters build the requests their providers document (mocked HTTP),
read the length, map errors to typed failures, and price by the second."""

import struct
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from followup_core.conversation.domain.llm import TokenUsage
from followup_core.conversation.domain.transcription import (
    TranscriptionError,
    TranscriptionFailure,
    ogg_opus_seconds,
)
from followup_core.conversation.domain.usage import AudioPrice, PriceBook, price_call
from followup_core.conversation.infrastructure.transcribers import (
    DEEPSEEK_URL,
    OPENAI_URL,
    DeepSeekTranscriber,
    OpenAiTranscriber,
    build_transcriber,
    parse_transcribe_spec,
)


def ogg_opus(seconds: float) -> bytes:
    head = b"OggS" + bytes(22) + b"OpusHead" + b"\x01\x01" + struct.pack("<H", 312) + bytes(8)
    last = b"OggS\x00\x04" + struct.pack("<q", int(seconds * 48_000) + 312) + bytes(16)
    return head + last


class Recorder:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        return self.response


def _fields(request: httpx.Request) -> bytes:
    return request.content


def test_openai_posts_the_file_and_gpt_transcribe_without_a_language() -> None:
    recorder = Recorder(httpx.Response(200, json={"text": " Hola, busco en Palermo ", "usage": {}}))
    transcriber = OpenAiTranscriber(
        "gpt-transcribe", "sk-test", transport=httpx.MockTransport(recorder)
    )

    transcript = transcriber.transcribe(ogg_opus(7.5), "audio/ogg; codecs=opus")

    (request,) = recorder.requests
    assert str(request.url) == OPENAI_URL == "https://api.openai.com/v1/audio/transcriptions"
    assert request.method == "POST"
    assert request.headers["Authorization"] == "Bearer sk-test"
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    body = _fields(request)
    assert b'name="model"\r\n\r\ngpt-transcribe' in body
    assert b'name="response_format"\r\n\r\njson' in body
    assert b'filename="audio.ogg"' in body and b"Content-Type: audio/ogg" in body
    # gpt-transcribe detects the language; `language` and `languages` must not both go.
    assert b'name="language"' not in body
    assert transcript.text == "Hola, busco en Palermo"
    assert transcript.seconds == pytest.approx(7.5)  # read from the Ogg file
    assert transcriber.model_name == "openai:gpt-transcribe"


def test_openai_older_models_get_language_es_and_the_billed_duration() -> None:
    response = {"text": "Hola", "usage": {"type": "duration", "seconds": 12}}
    recorder = Recorder(httpx.Response(200, json=response))
    transcriber = OpenAiTranscriber("whisper-1", "sk", transport=httpx.MockTransport(recorder))

    transcript = transcriber.transcribe(b"not-ogg", "audio/ogg")

    assert b'name="language"\r\n\r\nes' in _fields(recorder.requests[0])
    assert transcript.seconds == 12


def test_deepseek_posts_only_the_file_and_reads_duration_ms() -> None:
    response = {"request_id": "r1", "text": "Quiero visitar", "duration_ms": 3200}
    recorder = Recorder(httpx.Response(200, json=response))
    transcriber = DeepSeekTranscriber("asr", "ds-key", transport=httpx.MockTransport(recorder))

    transcript = transcriber.transcribe(ogg_opus(3), "audio/ogg; codecs=opus")

    (request,) = recorder.requests
    assert str(request.url) == DEEPSEEK_URL == "https://api.deepseek.com/v1/tools/asr"
    assert request.headers["Authorization"] == "Bearer ds-key"
    body = _fields(request)
    assert b'name="file"; filename="audio.ogg"' in body
    # No model and no language fields: DeepSeek documents neither.
    assert b'name="model"' not in body and b'name="language"' not in body
    assert transcript.text == "Quiero visitar"
    assert transcript.seconds == pytest.approx(3.2)
    assert transcriber.model_name == "deepseek:asr"


@pytest.mark.parametrize(
    ("status", "failure", "retryable"),
    [
        (429, TranscriptionFailure.PROVIDER_ERROR, True),
        (503, TranscriptionFailure.PROVIDER_ERROR, True),
        (408, TranscriptionFailure.PROVIDER_ERROR, True),
        (400, TranscriptionFailure.UNSUPPORTED, False),
        (413, TranscriptionFailure.TOO_LONG, False),
        (401, TranscriptionFailure.PROVIDER_ERROR, False),
    ],
)
def test_errors_are_typed(status: int, failure: TranscriptionFailure, retryable: bool) -> None:
    recorder = Recorder(httpx.Response(status, json={"error": "x"}))
    transcriber = DeepSeekTranscriber("asr", "k", transport=httpx.MockTransport(recorder))

    with pytest.raises(TranscriptionError) as raised:
        transcriber.transcribe(b"x", "audio/ogg")

    assert (raised.value.failure, raised.value.retryable) == (failure, retryable)


def test_a_timeout_is_retryable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    transcriber = OpenAiTranscriber("gpt-transcribe", "k", transport=httpx.MockTransport(timeout))

    with pytest.raises(TranscriptionError) as raised:
        transcriber.transcribe(b"x", "audio/ogg")

    assert raised.value.retryable


def test_the_setting_names_providers_that_cannot_transcribe() -> None:
    with pytest.raises(
        ValueError, match="anthropic does not transcribe audio; use openai, deepseek"
    ):
        parse_transcribe_spec("anthropic:claude-haiku-5-5")
    with pytest.raises(ValueError, match="mimo does not transcribe WhatsApp audio"):
        parse_transcribe_spec("mimo:mimo-v2.5-asr")
    with pytest.raises(ValueError, match="provider:model"):
        parse_transcribe_spec("openai")
    assert parse_transcribe_spec("deepseek:asr").api_key_env == "DEEPSEEK_API_KEY"
    assert parse_transcribe_spec("openai:gpt-transcribe").api_key_env == "OPENAI_API_KEY"
    assert build_transcriber("", "") is None


def test_ogg_opus_length_comes_from_the_last_granule() -> None:
    assert ogg_opus_seconds(ogg_opus(119.5)) == pytest.approx(119.5)
    assert ogg_opus_seconds(b"ID3 an mp3") is None


def test_audio_is_priced_by_the_second_with_its_own_price() -> None:
    prices = PriceBook(
        audio_prices=[AudioPrice("deepseek:asr", date(2026, 11, 21), Decimal("0.058"))]
    )
    at = datetime(2026, 11, 22, tzinfo=UTC)

    priced = price_call(prices, "deepseek:asr", TokenUsage(), at, 61.2, "transcribe")

    # 62 started seconds at USD 0.058 per hour.
    assert priced.cost_usd == Decimal("0.000999")
    assert priced.price_version == "2026-11-21"
    assert price_call(prices, "openai:gpt-transcribe", TokenUsage(), at, 10, "transcribe") == (
        price_call(PriceBook(), "x:y", TokenUsage(), at)
    )
