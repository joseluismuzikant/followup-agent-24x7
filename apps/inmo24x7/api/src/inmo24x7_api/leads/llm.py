"""Builds the language model from settings and loads the versioned prompt files."""

import logging
from functools import lru_cache
from pathlib import Path

from followup_core.conversation.domain.llm import LanguageModel
from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
from followup_core.conversation.infrastructure.langchain_llm import (
    LangChainLanguageModel,
    PromptFile,
)
from followup_core.conversation.infrastructure.llm_providers import (
    build_chat_model,
    parse_model_spec,
)

from ..config import Settings

PROMPTS_DIR = Path(__file__).parent / "prompts"
EXTRACT_PROMPT = "extract.v1"
REPLY_PROMPT = "reply.v1"

logger = logging.getLogger("inmo24x7.llm")


@lru_cache
def load_prompt(name: str) -> PromptFile:
    return PromptFile(version=name, template=(PROMPTS_DIR / f"{name}.md").read_text("utf-8"))


def build_language_model(settings: Settings) -> LanguageModel:
    if not settings.llm_model:
        logger.warning(
            "fake_llm_active",
            extra={"detail": "LLM_MODEL is not set: replies come from templates (development)."},
        )
        return FakeLanguageModel()
    provider, model = parse_model_spec(settings.llm_model)
    chat_model = build_chat_model(
        provider,
        model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        base_url=settings.llm_base_url or None,
    )
    return LangChainLanguageModel(
        chat_model,
        model_name=settings.llm_model,
        extract=load_prompt(EXTRACT_PROMPT),
        reply=load_prompt(REPLY_PROMPT),
    )
