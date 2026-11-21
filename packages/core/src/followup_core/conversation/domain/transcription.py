"""Speech to text for voice notes: the port, its result and its errors.

The audio itself is never stored: only the transcript, on the message. A provider is chosen
with TRANSCRIBE_MODEL ("provider:model"; empty = off), like LLM_MODEL.
"""

import struct
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class TranscriptionFailure(StrEnum):
    TOO_LONG = "too_long"  # over TRANSCRIBE_MAX_SECONDS or the size cap
    UNSUPPORTED = "unsupported"  # a format the provider does not take
    PROVIDER_ERROR = "provider_error"


class TranscriptionError(Exception):
    """A typed failure; `retryable` ones (429, 5xx, timeouts) go through the job backoff."""

    def __init__(self, failure: TranscriptionFailure, *, retryable: bool = False) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    # The audio's length (the provider's when it says, otherwise read from the file);
    # None when neither knows it. Transcription is billed by it.
    seconds: float | None


class Transcriber(Protocol):
    @property
    def model_name(self) -> str:
        """TRANSCRIBE_MODEL as configured ("openai:gpt-transcribe"), for the usage rows."""
        ...

    def transcribe(self, audio: bytes, mime_type: str) -> Transcript: ...


def ogg_opus_seconds(audio: bytes) -> float | None:
    """The length of an Ogg Opus file (WhatsApp voice notes), from its last page's granule
    position minus the pre-skip, at Opus's fixed 48 kHz. None when it is not Ogg Opus."""
    if not audio.startswith(b"OggS"):
        return None
    head = audio.find(b"OpusHead")
    last = audio.rfind(b"OggS")
    if head < 0 or last < 0 or len(audio) < last + 14 or len(audio) < head + 12:
        return None
    (pre_skip,) = struct.unpack_from("<H", audio, head + 10)
    (granule,) = struct.unpack_from("<q", audio, last + 6)
    if granule <= 0:
        return None
    return max(granule - pre_skip, 0) / 48_000
