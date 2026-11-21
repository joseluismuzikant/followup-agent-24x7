"""Speech-to-text providers selected by TRANSCRIBE_MODEL ("provider:model"), with the same API
key variables as LLM_MODEL. Tests mock them at the HTTP level (httpx.MockTransport); nothing
here logs the audio, the transcript or a key.

- openai: POST https://api.openai.com/v1/audio/transcriptions (multipart: file, model;
  `gpt-transcribe` detects the language, older models take `language=es`). Up to 25 MB;
  takes ogg. https://developers.openai.com/api/docs/guides/speech-to-text
- deepseek: POST https://api.deepseek.com/v1/tools/asr (multipart: file only; no model, the
  language is detected). 16-bit PCM WAV or Ogg Opus, at most 120 s and 8 MiB; the response
  has `text` and `duration_ms`. https://api-docs.deepseek.com/guides/asr
- fake: development and tests (no network).

Not transcribers: anthropic (Claude takes no audio input) and mimo (its ASR model takes only
mp3 and wav, and WhatsApp voice notes are Ogg Opus).
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from ..domain.transcription import (
    Transcript,
    TranscriptionError,
    TranscriptionFailure,
    ogg_opus_seconds,
)
from .llm_providers import PROVIDERS

logger = logging.getLogger("followup.transcription")

DEFAULT_TIMEOUT_SECONDS = 60.0
OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
DEEPSEEK_URL = "https://api.deepseek.com/v1/tools/asr"
# Models that take the singular `language` field (gpt-transcribe detects it, and its
# `languages` list must not be sent with `language`).
_OPENAI_LANGUAGE_MODELS = ("whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe")
# (what it cannot do, why): "anthropic does not transcribe audio; use openai, deepseek (…)".
_NOT_TRANSCRIBERS = {
    "anthropic": ("does not transcribe audio", "Claude takes no audio input"),
    "mimo": (
        "does not transcribe WhatsApp audio",
        "its ASR model takes only mp3 and wav; voice notes are Ogg Opus",
    ),
    "kimi": ("does not transcribe audio", "no speech-to-text API"),
}
TRANSCRIBE_PROVIDERS = ("openai", "deepseek")


@dataclass(frozen=True, slots=True)
class TranscriberSpec:
    provider: str
    model: str
    api_key_env: str | None


def parse_transcribe_spec(spec: str) -> TranscriberSpec:
    """Splits "provider:model". Raises ValueError with a clear message otherwise."""
    name, _, model = spec.partition(":")
    name, model = name.strip().lower(), model.strip()
    supported = ", ".join(TRANSCRIBE_PROVIDERS)
    if name in _NOT_TRANSCRIBERS:
        cannot, why = _NOT_TRANSCRIBERS[name]
        raise ValueError(f"TRANSCRIBE_MODEL: {name} {cannot}; use {supported} ({why}).")
    if name == "fake":
        return TranscriberSpec("fake", model or "fake", None)
    if name not in TRANSCRIBE_PROVIDERS or not model:
        raise ValueError(
            f"TRANSCRIBE_MODEL must look like 'provider:model' with one of: {supported} "
            "(for example openai:gpt-transcribe or deepseek:asr)."
        )
    return TranscriberSpec(name, model, PROVIDERS[name].api_key_env)


def _file_name(mime_type: str) -> str:
    """OpenAI picks the decoder from the file name's extension."""
    base = mime_type.split(";")[0].strip().lower()
    extension = {
        "audio/ogg": "ogg",
        "audio/opus": "ogg",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
        "audio/aac": "m4a",
        "audio/amr": "amr",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/webm": "webm",
    }.get(base, "ogg")
    return f"audio.{extension}"


def _post(
    client: httpx.Client,
    url: str,
    api_key: str,
    files: Mapping[str, Any],
    data: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        response = client.post(
            url, headers={"Authorization": f"Bearer {api_key}"}, files=files, data=data
        )
    except httpx.TimeoutException as error:
        raise TranscriptionError(TranscriptionFailure.PROVIDER_ERROR, retryable=True) from error
    except httpx.HTTPError as error:
        raise TranscriptionError(TranscriptionFailure.PROVIDER_ERROR, retryable=True) from error
    status = response.status_code
    if response.is_success:
        try:
            body = response.json()
        except ValueError as error:
            raise TranscriptionError(TranscriptionFailure.PROVIDER_ERROR) from error
        return body if isinstance(body, dict) else {}
    logger.warning("transcription_failed", extra={"status": status, "url": url})
    if status == 413:
        raise TranscriptionError(TranscriptionFailure.TOO_LONG)
    if status in (408, 429) or status >= 500:
        raise TranscriptionError(TranscriptionFailure.PROVIDER_ERROR, retryable=True)
    if status in (400, 415):
        raise TranscriptionError(TranscriptionFailure.UNSUPPORTED)
    raise TranscriptionError(TranscriptionFailure.PROVIDER_ERROR)


class OpenAiTranscriber:
    def __init__(
        self,
        model: str,
        api_key: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    @property
    def model_name(self) -> str:
        return f"openai:{self._model}"

    def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        data: dict[str, Any] = {"model": self._model, "response_format": "json"}
        if self._model in _OPENAI_LANGUAGE_MODELS:
            data["language"] = "es"
        body = _post(
            self._client,
            OPENAI_URL,
            self._api_key,
            {"file": (_file_name(mime_type), audio, mime_type.split(";")[0].strip())},
            data,
        )
        usage = body.get("usage") or {}
        seconds = usage.get("seconds") if usage.get("type") == "duration" else None
        return Transcript(
            str(body.get("text") or "").strip(),
            float(seconds) if seconds is not None else ogg_opus_seconds(audio),
        )


class DeepSeekTranscriber:
    def __init__(
        self,
        model: str,
        api_key: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        # DeepSeek's ASR has no model parameter: the name is only for the usage rows.
        self._model = model
        self._api_key = api_key
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    @property
    def model_name(self) -> str:
        return f"deepseek:{self._model}"

    def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        body = _post(
            self._client,
            DEEPSEEK_URL,
            self._api_key,
            {"file": (_file_name(mime_type), audio, mime_type.split(";")[0].strip())},
            {},
        )
        duration_ms = body.get("duration_ms")
        return Transcript(
            str(body.get("text") or "").strip(),
            duration_ms / 1000 if isinstance(duration_ms, int | float) else ogg_opus_seconds(audio),
        )


class FakeTranscriber:
    """No network: the audio bytes are the "spoken" text when they are UTF-8 (tests and
    scripts/simulate_whatsapp.py), a fixed sentence otherwise. `fail_with` makes it fail."""

    FIXED = "Hola, te mando un audio de prueba."

    def __init__(self, fail_with: TranscriptionError | None = None, model: str = "fake") -> None:
        self.fail_with = fail_with
        self.calls = 0
        self._model = model

    @property
    def model_name(self) -> str:
        return f"fake:{self._model}"

    def transcribe(self, audio: bytes, mime_type: str) -> Transcript:
        self.calls += 1
        if self.fail_with is not None:
            raise self.fail_with
        try:
            text = audio.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = ""
        return Transcript(text or self.FIXED, ogg_opus_seconds(audio) or 3.0)


def build_transcriber(spec: str, api_key: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS):
    """The configured transcriber, or None when TRANSCRIBE_MODEL is empty (feature off)."""
    if not spec:
        return None
    parsed = parse_transcribe_spec(spec)
    if parsed.provider == "fake":
        return FakeTranscriber(model=parsed.model)
    if parsed.provider == "openai":
        return OpenAiTranscriber(parsed.model, api_key, timeout_seconds)
    return DeepSeekTranscriber(parsed.model, api_key, timeout_seconds)
