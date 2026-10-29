"""The language model port.

It has two narrow operations instead of free-form chat: the graph decides the flow in
code, and the model only reads values out of a message or words a reply for an intent the
graph already chose.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from followup_core.tenancy.domain.agent_config import QualificationQuestion, Tone

from .thread import Author

# `asked_key` values for the two things every follow-up agent collects besides questions.
NAME_KEY = "visitor_name"
CONTACT_KEY = "contact"


class ReplyIntent(StrEnum):
    """What a reply must do. The graph picks it; the model only words it."""

    GREET = "greet"  # introduce the agent, then ask `question` if there is one
    ASK = "ask"  # ask exactly `question`
    PRESENT_OPTIONS = "present_options"  # short line before property cards
    NO_OPTIONS = "no_options"  # nothing matched yet
    ASK_NAME = "ask_name"
    ASK_CONTACT = "ask_contact"
    CLOSE = "close"  # thank them; someone from the team follows up
    AFTER_CLOSE = "after_close"  # anything after closing


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens
        )


@dataclass(frozen=True, slots=True)
class TranscriptLine:
    author: Author
    text: str


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    questions: Sequence[QualificationQuestion]
    transcript: Sequence[TranscriptLine]
    latest: str
    asked_key: str | None = None
    wants_name: bool = False
    wants_contact: bool = False


@dataclass(frozen=True, slots=True)
class Extraction:
    """Raw values by question key. The caller validates them with `parse_answer`."""

    values: Mapping[str, Any] = field(default_factory=dict)
    visitor_name: str | None = None
    contact: str | None = None
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True, slots=True)
class ReplyRequest:
    intent: ReplyIntent
    tone: Tone
    agent_name: str
    business_name: str
    question: QualificationQuestion | None = None
    facts: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    usage: TokenUsage = TokenUsage()


class LanguageModel(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def prompt_versions(self) -> Mapping[str, str]: ...

    def extract(self, request: ExtractionRequest) -> Extraction:
        """Raises LlmUnavailableError on timeout or provider failure."""
        ...

    def compose_reply(self, request: ReplyRequest) -> Reply:
        """Raises LlmUnavailableError on timeout or provider failure."""
        ...
