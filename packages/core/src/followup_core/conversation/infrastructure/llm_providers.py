"""LLM providers selected by LLM_MODEL ("provider:model").

Kimi (Moonshot) and MiMo (Xiaomi) expose OpenAI-compatible APIs, so they run through the
OpenAI integration with their own base URL and key. LLM_BASE_URL overrides the default URL
(for example the China endpoints or MiMo's Token Plan).

LLM_REASONING_EFFORT only reaches OpenAI's GPT-5 models (`reasoning_effort`); every other
provider and model ignores it. Some GPT-5 models do not accept "minimal" (GPT-5.4 starts at
"none"): when the API rejects it, the call is retried with "low" and the model keeps "low".
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

logger = logging.getLogger("followup.llm")

REASONING_EFFORTS = ("minimal", "low")
FALLBACK_EFFORT = "low"


@dataclass(frozen=True, slots=True)
class LlmProvider:
    name: str
    langchain_provider: str
    api_key_env: str
    default_base_url: str | None = None


PROVIDERS = {
    provider.name: provider
    for provider in (
        LlmProvider("anthropic", "anthropic", "ANTHROPIC_API_KEY"),
        LlmProvider("openai", "openai", "OPENAI_API_KEY"),
        LlmProvider("deepseek", "deepseek", "DEEPSEEK_API_KEY"),
        LlmProvider("kimi", "openai", "MOONSHOT_API_KEY", "https://api.moonshot.ai/v1"),
        LlmProvider("mimo", "openai", "MIMO_API_KEY", "https://api.xiaomimimo.com/v1"),
    )
}


def parse_model_spec(spec: str) -> tuple[LlmProvider, str]:
    """Splits "provider:model" and looks the provider up. Raises ValueError otherwise."""
    name, _, model = spec.partition(":")
    provider = PROVIDERS.get(name.strip().lower())
    if provider is None or not model.strip():
        supported = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"LLM_MODEL must look like 'provider:model' with one of: {supported}.")
    return provider, model.strip()


def takes_reasoning_effort(provider: LlmProvider, model: str) -> bool:
    """OpenAI's own GPT-5 family only (not Kimi or MiMo, which share the OpenAI client)."""
    return provider.name == "openai" and model.lower().startswith("gpt-5")


def rejects_reasoning_effort(error: Exception) -> bool:
    """A 400 from the API about the reasoning effort value (not a timeout, a rate limit or
    any other bad request)."""
    return getattr(error, "status_code", None) == 400 and "reasoning" in str(error).lower()


class ReasoningEffortFallback:
    """Calls the model with the configured effort; if the API rejects that value, retries
    the same call with "low" and uses "low" from then on, so the turn never fails for it."""

    def __init__(self, primary: BaseChatModel, fallback: Callable[[], BaseChatModel]) -> None:
        self._primary = primary
        self._make_fallback = fallback
        self._fallback: BaseChatModel | None = None
        self._lock = threading.Lock()

    def invoke(self, input: list[BaseMessage], *args: Any, **kwargs: Any) -> BaseMessage:
        if self._fallback is not None:
            return self._fallback.invoke(input, *args, **kwargs)
        try:
            return self._primary.invoke(input, *args, **kwargs)
        except Exception as error:
            if not rejects_reasoning_effort(error):
                raise
            with self._lock:
                if self._fallback is None:
                    logger.warning(
                        "llm_reasoning_effort_fallback",
                        extra={"detail": "The model rejected the reasoning effort; using low."},
                    )
                    self._fallback = self._make_fallback()
            return self._fallback.invoke(input, *args, **kwargs)


def build_chat_model(
    provider: LlmProvider,
    model: str,
    api_key: str,
    timeout_seconds: float,
    base_url: str | None = None,
    reasoning_effort: str | None = None,
) -> BaseChatModel | ReasoningEffortFallback:
    url = base_url or provider.default_base_url

    def build(**extra: Any) -> BaseChatModel:
        if url is not None:
            extra["base_url"] = url
        return init_chat_model(
            model,
            model_provider=provider.langchain_provider,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=1,
            **extra,
        )

    if not reasoning_effort or not takes_reasoning_effort(provider, model):
        return build()
    primary = build(reasoning_effort=reasoning_effort)
    if reasoning_effort == FALLBACK_EFFORT:
        return primary
    return ReasoningEffortFallback(primary, lambda: build(reasoning_effort=FALLBACK_EFFORT))
