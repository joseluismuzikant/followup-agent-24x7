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
