"""The agent's chat model gets LLM_REASONING_EFFORT only for OpenAI's GPT-5 models. A fake
init_chat_model records the kwargs: no provider is called."""

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from followup_core.conversation.infrastructure import llm_providers
from followup_platform.billing.prices import load_prices
from inmo24x7_api.config import get_settings
from inmo24x7_api.leads.llm import build_language_model


@pytest.fixture
def built(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_init(model: str, **kwargs: Any) -> object:
        calls.append({"model": model, **kwargs})
        return object()

    monkeypatch.setattr(llm_providers, "init_chat_model", fake_init)
    return calls


@pytest.mark.parametrize(
    ("model", "effort", "expected"),
    [
        ("openai:gpt-5.4-nano", "low", "low"),
        ("openai:gpt-5.4-mini", "minimal", "minimal"),
        ("openai:gpt-5.4-mini", "", None),
        ("anthropic:claude-sonnet-5-5", "low", None),
        ("deepseek:deepseek-chat", "low", None),
    ],
)
def test_the_setting_reaches_only_openai_gpt5(built, model, effort, expected) -> None:
    settings = dataclasses.replace(
        get_settings(), llm_model=model, llm_api_key="sk-test", llm_reasoning_effort=effort
    )

    build_language_model(settings)

    assert built[0].get("reasoning_effort") == expected


@pytest.mark.parametrize(
    ("model", "prices"),
    [
        ("openai:gpt-5.4-nano", ("0.20", "1.25", "0.02")),
        ("openai:gpt-5.4-mini", ("0.75", "4.50", "0.075")),
    ],
)
def test_gpt54_small_models_are_priced(model, prices) -> None:
    price = load_prices().price_for(model, datetime(2026, 11, 16, 12, tzinfo=UTC))

    assert price is not None
    assert (price.input_per_mtok, price.output_per_mtok, price.cached_input_per_mtok) == tuple(
        Decimal(value) for value in prices
    )
    assert price.source == "https://developers.openai.com/api/docs/pricing"
