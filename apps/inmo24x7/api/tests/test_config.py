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
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
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


def test_production_requires_supabase_jwt_secret(monkeypatch) -> None:
    _production_env(
        monkeypatch,
        database_url="postgresql+psycopg://db/app",
        cors="https://app.example.com",
    )
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    with pytest.raises(ConfigurationError, match="SUPABASE_JWT_SECRET"):
        get_settings()


def test_startup_fails_fast_without_production_database() -> None:
    env = os.environ.copy()
    env["APP_ENV"] = "production"
    env["CORS_ORIGINS"] = "https://app.example.com"
    env["SUPABASE_URL"] = "https://example.supabase.co"
    env["SUPABASE_ANON_KEY"] = "anon-key"
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
