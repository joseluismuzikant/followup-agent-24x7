"""LLM_REASONING_EFFORT reaches only OpenAI's GPT-5 models, and a rejected "minimal" falls
back to "low" without failing the call. No real provider is called: init_chat_model is
replaced by a fake that records its kwargs."""

from typing import Any

import pytest
from followup_core.conversation.infrastructure import llm_providers
from followup_core.conversation.infrastructure.llm_providers import (
    ReasoningEffortFallback,
    build_chat_model,
    parse_model_spec,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class FakeChatModel:
    def __init__(self, kwargs: dict[str, Any], fail_with: Exception | None = None) -> None:
        self.kwargs = kwargs
        self.fail_with = fail_with
        self.calls: list[list[BaseMessage]] = []

    def invoke(self, input: list[BaseMessage], *args: Any, **kwargs: Any) -> BaseMessage:
        self.calls.append(input)
        if self.fail_with is not None:
            raise self.fail_with
        return AIMessage(f"effort={self.kwargs.get('reasoning_effort')}")


class ApiError(Exception):
    """Shaped like openai.APIStatusError: a status code and the API's message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


REJECTED = ApiError(
    400,
    "Error code: 400 - Unsupported value: 'reasoning_effort' does not support 'minimal' with "
    "this model. Supported values are: 'none', 'low', 'medium', 'high' and 'xhigh'.",
)


@pytest.fixture
def built(monkeypatch) -> list[dict[str, Any]]:
    """Every init_chat_model call's kwargs, in order."""
    calls: list[dict[str, Any]] = []

    def fake_init(model: str, **kwargs: Any) -> FakeChatModel:
        calls.append({"model": model, **kwargs})
        return FakeChatModel(kwargs)

    monkeypatch.setattr(llm_providers, "init_chat_model", fake_init)
    return calls


def build(spec: str, effort: str | None, base_url: str | None = None) -> Any:
    provider, model = parse_model_spec(spec)
    return build_chat_model(
        provider, model, "sk-test", 20.0, base_url=base_url, reasoning_effort=effort
    )


@pytest.mark.parametrize("spec", ["openai:gpt-5.4-nano", "openai:gpt-5.4-mini", "openai:GPT-5"])
def test_openai_gpt5_models_get_the_reasoning_effort(built, spec) -> None:
    build(spec, "low")

    assert built[0]["reasoning_effort"] == "low"
    assert built[0]["model_provider"] == "openai"
    assert built[0]["timeout"] == 20.0


@pytest.mark.parametrize(
    "spec",
    [
        "openai:gpt-4.1-mini",
        "anthropic:claude-sonnet-5-5",
        "deepseek:deepseek-chat",
        # These run on the OpenAI client too, but they are not OpenAI's GPT-5.
        "kimi:gpt-5-lookalike",
        "mimo:mimo-v2-flash",
    ],
)
def test_other_providers_and_models_are_unchanged(built, spec) -> None:
    model = build(spec, "minimal")

    assert len(built) == 1
    assert "reasoning_effort" not in built[0]
    assert isinstance(model, FakeChatModel)


def test_without_the_setting_nothing_is_passed(built) -> None:
    build("openai:gpt-5.4-mini", None)

    assert "reasoning_effort" not in built[0]


def test_base_url_is_kept_with_the_effort(built) -> None:
    build("openai:gpt-5.4-mini", "low", base_url="https://proxy.example/v1")

    assert built[0]["base_url"] == "https://proxy.example/v1"
    assert built[0]["reasoning_effort"] == "low"


def test_minimal_is_tried_first_and_the_low_model_is_built_only_when_needed(built) -> None:
    model = build("openai:gpt-5.4-nano", "minimal")

    assert isinstance(model, ReasoningEffortFallback)
    assert [call["reasoning_effort"] for call in built] == ["minimal"]
    assert model.invoke([HumanMessage("Hola")]).content == "effort=minimal"
    assert len(built) == 1


def test_a_rejected_minimal_retries_with_low_and_keeps_low() -> None:
    primary = FakeChatModel({"reasoning_effort": "minimal"}, fail_with=REJECTED)
    fallbacks: list[FakeChatModel] = []

    def make_low() -> FakeChatModel:
        fallbacks.append(FakeChatModel({"reasoning_effort": "low"}))
        return fallbacks[-1]

    model = ReasoningEffortFallback(primary, make_low)  # pyright: ignore[reportArgumentType]

    assert model.invoke([HumanMessage("Hola")]).content == "effort=low"
    assert model.invoke([HumanMessage("¿Sigue disponible?")]).content == "effort=low"
    assert len(primary.calls) == 1  # "minimal" is not tried again
    assert len(fallbacks) == 1
    assert len(fallbacks[0].calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        ApiError(429, "Rate limit reached for gpt-5.4-nano"),
        ApiError(400, "This model's maximum context length is 400000 tokens."),
        TimeoutError("Request timed out."),
    ],
)
def test_other_errors_are_not_retried(error) -> None:
    primary = FakeChatModel({"reasoning_effort": "minimal"}, fail_with=error)
    model = ReasoningEffortFallback(
        primary,  # pyright: ignore[reportArgumentType]
        lambda: pytest.fail("the fallback must not be built"),
    )

    with pytest.raises(type(error)):
        model.invoke([HumanMessage("Hola")])
