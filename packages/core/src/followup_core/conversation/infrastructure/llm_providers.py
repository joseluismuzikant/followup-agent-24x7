"""LLM providers selected by LLM_MODEL ("provider:model").

Kimi (Moonshot) and MiMo (Xiaomi) expose OpenAI-compatible APIs, so they run through the
OpenAI integration with their own base URL and key. LLM_BASE_URL overrides the default URL
(for example the China endpoints or MiMo's Token Plan).
"""

from dataclasses import dataclass

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


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


def build_chat_model(
    provider: LlmProvider,
    model: str,
    api_key: str,
    timeout_seconds: float,
    base_url: str | None = None,
) -> BaseChatModel:
    url = base_url or provider.default_base_url
    if url is None:
        return init_chat_model(
            model,
            model_provider=provider.langchain_provider,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=1,
        )
    return init_chat_model(
        model,
        model_provider=provider.langchain_provider,
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=1,
        base_url=url,
    )
