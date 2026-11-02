"""The LangChain adapter keeps the flow's rules even when the model does not."""

import pytest
from followup_core.conversation.domain.llm import ReplyIntent, ReplyRequest
from followup_core.conversation.infrastructure.langchain_llm import (
    LangChainLanguageModel,
    PromptFile,
    strip_introduction,
)
from followup_core.tenancy.domain.agent_config import Tone
from langchain_core.language_models.fake_chat_models import FakeListChatModel


def _reply(model_text: str, intent: ReplyIntent) -> str:
    llm = LangChainLanguageModel(
        FakeListChatModel(responses=[model_text]),
        model_name="fake:list",
        extract=PromptFile("extract.test", "x"),
        reply=PromptFile("reply.test", "intent: $intent"),
    )
    request = ReplyRequest(intent, Tone.WARM, "Sofía", "Inmobiliaria Sur")
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
    assert _reply(intro, ReplyIntent.GREET) == intro
