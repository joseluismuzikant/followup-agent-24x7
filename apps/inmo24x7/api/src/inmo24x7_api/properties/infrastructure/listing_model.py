"""The model that reads a listing's text (LLM_MODEL), and its fake for development and tests.

The prompt (prompts/listing_extract.v<n>.md) asks for a JSON object with Spanish keys; they
are turned into our field names here and validated by listing_page.map_values.
"""

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from followup_core.conversation.domain.errors import LlmUnavailableError
from followup_core.conversation.infrastructure.langchain_llm import (
    ChatModel,
    _content,  # pyright: ignore[reportPrivateUsage]
    _parse_json,  # pyright: ignore[reportPrivateUsage]
    _usage,  # pyright: ignore[reportPrivateUsage]
)
from followup_core.conversation.infrastructure.llm_providers import (
    build_chat_model,
    parse_model_spec,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ...config import Settings
from ..application.listing_page import conditions_in, operation_in, rooms_in
from ..domain.listing import ModelReading

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
LISTING_PROMPT = "listing_extract.v1"

# The prompt's keys -> our field names (the conditions already use ours).
_KEYS = {
    "titulo": "title",
    "direccion": "address",
    "operacion": "operation",
    "zona": "zone",
    "precio": "price",
    "moneda": "currency",
    "ambientes": "rooms",
}


def our_names(values: Mapping[str, Any]) -> dict[str, Any]:
    return {_KEYS.get(key, key): value for key, value in values.items() if value is not None}


@lru_cache
def load_listing_prompt(name: str = LISTING_PROMPT) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text("utf-8")


class LangChainListingModel:
    def __init__(self, chat_model: ChatModel, model_name: str, prompt: str = LISTING_PROMPT):
        self._chat_model = chat_model
        self._model_name = model_name
        self._prompt = prompt

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def prompt_version(self) -> str:
        return self._prompt

    def read(self, text: str) -> ModelReading:
        messages = [SystemMessage(load_listing_prompt(self._prompt)), HumanMessage(text)]
        try:
            result = self._chat_model.invoke(messages)
        except Exception as error:  # timeouts, rate limits, provider outages
            raise LlmUnavailableError(f"{type(error).__name__} from the model provider.") from error
        if not isinstance(result, AIMessage):
            raise LlmUnavailableError("The model returned an unexpected message type.")
        return ModelReading(our_names(_parse_json(_content(result))), _usage(result))


_PRICE = re.compile(
    r"(?P<currency>u\$s|us\$|usd|\$)\s*(?P<amount>\d{1,3}(?:\.\d{3})+|\d{4,})", re.IGNORECASE
)
_EXPENSAS = re.compile(r"\bexpensas\b", re.IGNORECASE)
_ZONE = re.compile(r"\b(?:barrio|zona|ubicaci[oó]n)\s*:\s*(?P<zone>[^\n,.]{2,60})", re.IGNORECASE)
_STREET = re.compile(r"\b(?:direcci[oó]n)\s*:\s*(?P<address>[^\n]{3,120})", re.IGNORECASE)


class FakeListingModel:
    """No network: `answer` when given (tests), otherwise simple rules over the text
    (development without LLM_MODEL). `fail` makes it raise LlmUnavailableError."""

    def __init__(
        self, answer: Mapping[str, Any] | None = None, *, fail: bool = False, model: str = "fake"
    ) -> None:
        self.answer = answer
        self.fail = fail
        self.texts: list[str] = []
        self._model = model

    @property
    def model_name(self) -> str:
        return f"fake:{self._model}"

    @property
    def prompt_version(self) -> str:
        return LISTING_PROMPT

    def read(self, text: str) -> ModelReading:
        self.texts.append(text)
        if self.fail:
            raise LlmUnavailableError("fake listing model failure")
        if self.answer is not None:
            return ModelReading(our_names(self.answer))
        found: dict[str, Any] = {}
        # The expensas line has a price that is not the listing's.
        lines = [
            cut
            for line in text.splitlines()
            if (cut := _EXPENSAS.split(line, maxsplit=1)[0].strip(" .:+-"))
        ]
        title = next((line for line in lines if len(line) > 10 and not _PRICE.search(line)), "")
        if title:
            found["title"] = title[:120]
        priced = "\n".join(lines)
        if operation := operation_in(text):
            found["operation"] = operation.value
        if rooms := rooms_in(text):
            found["rooms"] = rooms
        if price := _PRICE.search(priced):
            found["price"] = price.group("amount")
            found["currency"] = "ARS" if price.group("currency") == "$" else "USD"
        if zone := _ZONE.search(text):
            found["zone"] = zone.group("zone").strip()
        if street := _STREET.search(text):
            found["address"] = street.group("address").strip()
        found.update(conditions_in(text))
        return ModelReading(found)


def build_listing_model(settings: Settings):
    """LLM_MODEL's chat model with the listing prompt, or the fake one without LLM_MODEL."""
    if not settings.llm_model:
        return FakeListingModel()
    provider, model = parse_model_spec(settings.llm_model)
    chat_model = build_chat_model(
        provider,
        model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        base_url=settings.llm_base_url or None,
        reasoning_effort=settings.llm_reasoning_effort or None,
    )
    return LangChainListingModel(chat_model, settings.llm_model)
