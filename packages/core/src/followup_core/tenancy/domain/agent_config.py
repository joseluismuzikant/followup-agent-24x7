import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .errors import InvalidAgentNameError, InvalidQuestionsError

MAX_AGENT_NAME_LENGTH = 40
MAX_QUESTIONS = 10
MAX_LABEL_LENGTH = 120
_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_CUSTOM_KEY_PATTERN = re.compile(r"^custom_([1-9][0-9]*)$")


def custom_key(number: int) -> str:
    return f"custom_{number}"


def custom_key_number(key: str) -> int | None:
    """The n in `custom_<n>`, or None when the key is not a custom question key."""
    match = _CUSTOM_KEY_PATTERN.fullmatch(key)
    return int(match.group(1)) if match else None


class Tone(StrEnum):
    WARM = "warm"
    PROFESSIONAL = "professional"
    FORMAL = "formal"


class AfterHoursMode(StrEnum):
    KEEP_ANSWERING_AND_PROPOSE_VISIT = "keep_answering_and_propose_visit"


class QuestionKind(StrEnum):
    CHOICE = "choice"
    TEXT = "text"
    NUMBER = "number"
    MONEY = "money"
    BOOLEAN = "boolean"


@dataclass(frozen=True, slots=True)
class QualificationQuestion:
    """One thing the agent asks a lead. `key` is the stable name the graph fills in."""

    key: str
    label: str
    kind: QuestionKind
    options: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        if not _KEY_PATTERN.fullmatch(self.key):
            raise InvalidQuestionsError(f"Question key '{self.key}' is not a valid slug.")
        label = self.label.strip()
        if not label or len(label) > MAX_LABEL_LENGTH:
            raise InvalidQuestionsError("Question label must have 1 to 120 characters.")
        object.__setattr__(self, "label", label)

        options = tuple(option.strip() for option in self.options if option.strip())
        if self.kind is QuestionKind.CHOICE:
            if len(set(options)) < 2:
                raise InvalidQuestionsError("A choice question needs at least two options.")
        else:
            options = ()
        object.__setattr__(self, "options", options)


@dataclass(frozen=True, slots=True)
class AgentConfig:
    agent_name: str
    tone: Tone
    after_hours_mode: AfterHoursMode
    qualification_questions: tuple[QualificationQuestion, ...]

    def __post_init__(self) -> None:
        name = self.agent_name.strip()
        if not name or len(name) > MAX_AGENT_NAME_LENGTH:
            raise InvalidAgentNameError("Agent name must have 1 to 40 characters.")
        object.__setattr__(self, "agent_name", name)

        questions = tuple(self.qualification_questions)
        if len(questions) > MAX_QUESTIONS:
            raise InvalidQuestionsError(f"At most {MAX_QUESTIONS} questions are allowed.")
        keys = [question.key for question in questions]
        if len(set(keys)) != len(keys):
            raise InvalidQuestionsError("Question keys must be unique.")
        object.__setattr__(self, "qualification_questions", questions)

    def to_primitives(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "tone": self.tone.value,
            "after_hours_mode": self.after_hours_mode.value,
            "qualification_questions": [
                {
                    "key": question.key,
                    "label": question.label,
                    "kind": question.kind.value,
                    "options": list(question.options),
                    "enabled": question.enabled,
                }
                for question in self.qualification_questions
            ],
        }

    @classmethod
    def from_primitives(cls, data: Mapping[str, Any]) -> "AgentConfig":
        raw_questions: Sequence[Mapping[str, Any]] = data["qualification_questions"]
        return cls(
            agent_name=data["agent_name"],
            tone=Tone(data["tone"]),
            after_hours_mode=AfterHoursMode(data["after_hours_mode"]),
            qualification_questions=tuple(
                QualificationQuestion(
                    key=question["key"],
                    label=question["label"],
                    kind=QuestionKind(question["kind"]),
                    options=tuple(question.get("options", ())),
                    enabled=question.get("enabled", True),
                )
                for question in raw_questions
            ),
        )
