"""The LangChain adapter keeps the flow's rules even when the model does not."""

import pytest
from followup_core.conversation.domain.llm import ReplyIntent, ReplyRequest, TokenUsage
from followup_core.conversation.infrastructure.langchain_llm import (
    LangChainLanguageModel,
    PromptFile,
    _usage,
    strip_introduction,
    strip_trailing_question,
)
from followup_core.tenancy.domain.agent_config import QualificationQuestion, QuestionKind, Tone
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

BUDGET = QualificationQuestion(key="budget", label="Presupuesto", kind=QuestionKind.MONEY)


def _reply(
    model_text: str, intent: ReplyIntent, question: QualificationQuestion | None = None
) -> str:
    llm = LangChainLanguageModel(
        FakeListChatModel(responses=[model_text]),
        model_name="fake:list",
        extract=PromptFile("extract.test", "x"),
        reply=PromptFile("reply.test", "intent: $intent"),
    )
    request = ReplyRequest(intent, Tone.WARM, "Sofía", "Inmobiliaria Sur", question=question)
    return llm.compose_reply(request).text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "¡Hola! Soy Sofía, de Inmobiliaria Sur. ¿Me contás qué presupuesto tenés en mente?",
            "¿Me contás qué presupuesto tenés en mente?",
        ),
        (
            "Hola, soy Sofía de Inmobiliaria Sur. contame, ¿tenés crédito aprobado?",
            "Contame, ¿tenés crédito aprobado?",
        ),
        ("Soy Sofía! ¿Cuántos ambientes necesitás?", "¿Cuántos ambientes necesitás?"),
        (
            "¡Hola, Ana! Soy Sofía, de Inmobiliaria Sur. Para orientarte mejor, ¿qué presupuesto?",
            "Para orientarte mejor, ¿qué presupuesto?",
        ),
        # A plain greeting or someone else's name is not an introduction.
        ("¡Hola Ana! ¿Cuántos ambientes necesitás?", "¡Hola Ana! ¿Cuántos ambientes necesitás?"),
        ("Soy Sofía, de Inmobiliaria Sur.", "Soy Sofía, de Inmobiliaria Sur."),
        ("¿Qué presupuesto tenés?", "¿Qué presupuesto tenés?"),
    ],
)
def test_strip_introduction(text: str, expected: str) -> None:
    assert strip_introduction(text, "Sofía") == expected


def test_only_the_greeting_may_introduce_the_agent() -> None:
    intro = "¡Hola! Soy Sofía, de Inmobiliaria Sur. ¿Qué presupuesto tenés en mente?"

    assert _reply(intro, ReplyIntent.ASK) == "¿Qué presupuesto tenés en mente?"
    assert _reply(intro, ReplyIntent.GREET, BUDGET) == intro


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "¡Hola! Soy Sofía, de Inmobiliaria Sur. Contame, ¿qué estás buscando?",
            "¡Hola! Soy Sofía, de Inmobiliaria Sur.",
        ),
        (
            "¡Hola! Soy Sofía. Buenísimo, te busco opciones. ¿Algo más? ¿Qué zona?",
            "¡Hola! Soy Sofía. Buenísimo, te busco opciones.",
        ),
        ("¡Hola! Soy Sofía, de Inmobiliaria Sur.", "¡Hola! Soy Sofía, de Inmobiliaria Sur."),
        # Only a question: nothing would be left, so it stays.
        ("¿Qué estás buscando?", "¿Qué estás buscando?"),
    ],
)
def test_strip_trailing_question(text: str, expected: str) -> None:
    assert strip_trailing_question(text) == expected


def test_a_greeting_without_a_question_asks_nothing() -> None:
    model_text = "¡Hola! Soy Sofía, de Inmobiliaria Sur. Contame, ¿qué estás buscando?"

    assert _reply(model_text, ReplyIntent.GREET) == "¡Hola! Soy Sofía, de Inmobiliaria Sur."
    # With a question to ask, the closing question is the point of the message.
    assert _reply(model_text, ReplyIntent.GREET, BUDGET) == model_text


# Usage as each provider's LangChain integration reports it (built with the integrations'
# own converters, so a change in how they normalise usage breaks this test).
def _anthropic_usage() -> AIMessage:
    from anthropic.types import Usage
    from langchain_anthropic.chat_models import _create_usage_metadata

    usage = Usage(
        input_tokens=500,
        output_tokens=40,
        cache_read_input_tokens=1_000,
        cache_creation_input_tokens=0,
    )
    return AIMessage("x", usage_metadata=_create_usage_metadata(usage))


def _openai_usage() -> AIMessage:
    # OpenAI, and Kimi and MiMo through the OpenAI integration.
    from langchain_openai.chat_models.base import _create_usage_metadata

    usage = {
        "prompt_tokens": 1_500,
        "completion_tokens": 40,
        "total_tokens": 1_540,
        "prompt_tokens_details": {"cached_tokens": 1_000},
    }
    return AIMessage("x", usage_metadata=_create_usage_metadata(usage))


def _deepseek_usage() -> AIMessage:
    from langchain_deepseek.chat_models import _add_cache_read_tokens
    from langchain_openai.chat_models.base import _create_usage_metadata

    usage = {"prompt_tokens": 1_500, "completion_tokens": 40, "total_tokens": 1_540}
    message = AIMessage("x", usage_metadata=_create_usage_metadata(usage))
    _add_cache_read_tokens(message, 1_000)
    return message


@pytest.mark.parametrize("message", [_anthropic_usage, _openai_usage, _deepseek_usage])
def test_usage_counts_cached_input_for_every_provider(message) -> None:
    usage = _usage(message())

    # input_tokens is the total, cached included.
    assert usage == TokenUsage(
        input_tokens=1_500, output_tokens=40, cached_input_tokens=1_000, reported=True
    )


def test_a_reply_without_usage_is_marked_as_not_reported() -> None:
    assert _usage(AIMessage("x")) == TokenUsage(reported=False)
    without_cache = _usage(
        AIMessage("x", usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5})
    )
    assert without_cache == TokenUsage(3, 2, 0, reported=True)
