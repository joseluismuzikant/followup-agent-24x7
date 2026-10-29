import os
import subprocess
import sys

import pytest
from inmo24x7_api.config import ConfigurationError, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _production_env(monkeypatch, *, database_url: str | None = None, cors: str | None = None):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("LLM_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)
    if cors is None:
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("CORS_ORIGINS", cors)


def test_development_uses_local_defaults(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    settings = get_settings()

    assert settings.database_url.endswith("localhost:5433/followup")
    assert settings.cors_origins == (
        "http://localhost:5173",
        "http://localhost:5174",
    )


def test_production_requires_database_url(monkeypatch) -> None:
    _production_env(monkeypatch, cors="https://app.example.com")

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        get_settings()


def test_production_requires_cors_origins(monkeypatch) -> None:
    _production_env(monkeypatch, database_url="postgresql+psycopg://db/app")

    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        get_settings()


def test_production_requires_supabase_secret_or_jwks(monkeypatch) -> None:
    _production_env(
        monkeypatch,
        database_url="postgresql+psycopg://db/app",
        cors="https://app.example.com",
    )
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)

    with pytest.raises(ConfigurationError, match="SUPABASE_JWT_SECRET or SUPABASE_JWKS_URL"):
        get_settings()


def test_production_accepts_jwks_without_secret_or_anon_key(monkeypatch) -> None:
    _production_env(
        monkeypatch,
        database_url="postgresql+psycopg://db/app",
        cors="https://app.example.com",
    )
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv(
        "SUPABASE_JWKS_URL", "https://example.supabase.co/auth/v1/.well-known/jwks.json"
    )

    assert get_settings().supabase_jwks_url.endswith("jwks.json")


def test_production_requires_supabase_url(monkeypatch) -> None:
    _production_env(
        monkeypatch,
        database_url="postgresql+psycopg://db/app",
        cors="https://app.example.com",
    )
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="SUPABASE_URL"):
        get_settings()


def _complete_production_env(monkeypatch) -> None:
    _production_env(
        monkeypatch, database_url="postgresql+psycopg://db/app", cors="https://app.example.com"
    )


def test_development_without_llm_model_uses_the_fake_llm(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = get_settings()

    assert settings.llm_model == ""
    assert settings.llm_timeout_seconds == 20
    assert settings.simulator_daily_limit == 300


def test_production_requires_llm_model(monkeypatch) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.delenv("LLM_MODEL")

    with pytest.raises(ConfigurationError, match="LLM_MODEL must be set"):
        get_settings()


@pytest.mark.parametrize(
    ("model", "key_env"),
    [
        ("anthropic:claude-sonnet-5-5", "ANTHROPIC_API_KEY"),
        ("openai:gpt-5", "OPENAI_API_KEY"),
        ("deepseek:deepseek-chat", "DEEPSEEK_API_KEY"),
        ("kimi:kimi-k2.5", "MOONSHOT_API_KEY"),
        ("mimo:mimo-v2.5-pro", "MIMO_API_KEY"),
    ],
)
def test_llm_key_comes_from_the_provider_variable(monkeypatch, model: str, key_env: str) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", model)
    monkeypatch.delenv(key_env, raising=False)

    with pytest.raises(ConfigurationError, match=key_env):
        get_settings()

    get_settings.cache_clear()
    monkeypatch.setenv(key_env, "sk-provider")
    settings = get_settings()
    assert (settings.llm_model, settings.llm_api_key) == (model, "sk-provider")


def test_unknown_llm_provider_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LLM_MODEL", "gemini:pro")

    with pytest.raises(ConfigurationError, match="provider:model"):
        get_settings()


@pytest.mark.parametrize("name", ["LLM_TIMEOUT_SECONDS", "SIMULATOR_DAILY_LIMIT"])
def test_numeric_llm_settings_must_be_positive(monkeypatch, name: str) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(name, "0")

    with pytest.raises(ConfigurationError, match=name):
        get_settings()


def test_startup_fails_fast_without_production_database() -> None:
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env["CORS_ORIGINS"] = "https://app.example.com"
    env["SUPABASE_URL"] = "https://example.supabase.co"
    env["SUPABASE_JWT_SECRET"] = "jwt-secret"
    env.pop("DATABASE_URL", None)

    result = subprocess.run(
        [sys.executable, "-c", "import inmo24x7_api.main"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "DATABASE_URL must be set when APP_ENV=production." in result.stderr
