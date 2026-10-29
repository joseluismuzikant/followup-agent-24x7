"""Validation of the values an LLM extracts for qualification questions.

Both the real model and the fake one go through here, so a value that reaches the graph
state always matches its question's kind.
"""

import re
import unicodedata
from typing import Any

from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind

MAX_TEXT_ANSWER_LENGTH = 200
CURRENCIES = ("ARS", "USD")

AnswerValue = str | int | bool | dict[str, Any]


def normalize(text: str) -> str:
    """Lowercase without accents, for forgiving comparisons."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower().strip()


def _number(raw: Any) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        return int(raw) if raw >= 0 else None
    if isinstance(raw, str):
        digits = re.sub(r"[^\d]", "", raw)
        return int(digits) if digits else None
    return None


def parse_answer(question: QualificationQuestion, raw: Any) -> AnswerValue | None:
    """The validated value for `question`, or None when `raw` does not fit its kind."""
    if raw is None:
        return None
    match question.kind:
        case QuestionKind.CHOICE:
            if not isinstance(raw, str):
                return None
            wanted = normalize(raw)
            for option in question.options:
                if normalize(option) == wanted:
                    return option
            return None
        case QuestionKind.TEXT:
            if not isinstance(raw, str):
                return None
            text = " ".join(raw.split())
            return text if 0 < len(text) <= MAX_TEXT_ANSWER_LENGTH else None
        case QuestionKind.NUMBER:
            number = _number(raw)
            return number if number is not None and number < 1000 else None
        case QuestionKind.MONEY:
            if not isinstance(raw, dict):
                return None
            amount = _number(raw.get("amount"))
            currency = str(raw.get("currency", "")).upper()
            if amount is None or amount == 0 or currency not in CURRENCIES:
                return None
            return {"amount": amount, "currency": currency}
        case QuestionKind.BOOLEAN:
            return raw if isinstance(raw, bool) else None
