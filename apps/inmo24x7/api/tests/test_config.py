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


PRODUCTION_MESSAGING = {
    "META_APP_SECRET": "real-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "real-verify-token",
    "WHATSAPP_SENDER": "cloud",
    # base64 of 32 bytes, not the development key.
    "TOKEN_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    "SMTP_HOST": "smtp.example.com",
    "EMAIL_FROM": "inmo24x7 <avisos@example.com>",
    "PANEL_URL": "https://app.example.com",
    "META_APP_ID": "1234567890",
    "META_EMBEDDED_SIGNUP_CONFIG_ID": "987654321",
    "SUPPORT_EMAIL": "soporte@example.com",
}


def _production_env(monkeypatch, *, database_url: str | None = None, cors: str | None = None):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("LLM_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("AUTH_MODE", raising=False)
    for name, value in PRODUCTION_MESSAGING.items():
        monkeypatch.setenv(name, value)
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


def test_production_accepts_jwks_without_the_jwt_secret(monkeypatch) -> None:
    _production_env(
        monkeypatch,
        database_url="postgresql+psycopg://db/app",
        cors="https://app.example.com",
    )
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.setenv(
        "SUPABASE_JWKS_URL", "https://example.supabase.co/auth/v1/.well-known/jwks.json"
    )

    assert get_settings().supabase_jwks_url.endswith("jwks.json")


def test_production_needs_the_service_role_key_to_create_invited_users(monkeypatch) -> None:
    _production_env(
        monkeypatch,
        database_url="postgresql+psycopg://db/app",
        cors="https://app.example.com",
    )
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="SUPABASE_SERVICE_ROLE_KEY"):
        get_settings()


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


def test_development_defaults_to_dev_auth(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("AUTH_MODE", raising=False)

    assert get_settings().auth_mode == "dev"


def test_production_defaults_to_supabase_auth(monkeypatch) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.delenv("AUTH_MODE", raising=False)

    assert get_settings().auth_mode == "supabase"


def test_production_rejects_dev_auth(monkeypatch) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "dev")

    with pytest.raises(ConfigurationError, match="AUTH_MODE=dev is not allowed"):
        get_settings()


def test_unknown_auth_mode_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "anything")

    with pytest.raises(ConfigurationError, match="AUTH_MODE must be"):
        get_settings()


def test_supabase_auth_in_development_needs_a_verification_method(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    monkeypatch.delenv("SUPABASE_JWKS_URL", raising=False)

    with pytest.raises(ConfigurationError, match="AUTH_MODE=supabase needs"):
        get_settings()


def test_development_has_working_messaging_defaults(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    for name in PRODUCTION_MESSAGING:
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.whatsapp_sender == "log"
    assert settings.meta_graph_api_version == "v26.0"
    assert (settings.smtp_host, settings.smtp_port, settings.smtp_starttls) == (
        "localhost",
        1025,
        False,
    )
    assert settings.panel_url == "http://localhost:5173"
    # Without Embedded Signup locally: admins connect numbers by hand.
    assert (settings.meta_app_id, settings.meta_embedded_signup_config_id) == ("", "")
    assert settings.support_email == "soporte@inmo24x7.local"


@pytest.mark.parametrize("name", sorted(PRODUCTION_MESSAGING))
def test_production_requires_every_messaging_setting(monkeypatch, name: str) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.delenv(name)

    if name == "WHATSAPP_SENDER":
        # Defaults to cloud in production.
        assert get_settings().whatsapp_sender == "cloud"
        return
    with pytest.raises(ConfigurationError, match=name):
        get_settings()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("WHATSAPP_SENDER", "log", "WHATSAPP_SENDER must be 'cloud'"),
        ("TOKEN_ENCRYPTION_KEY", "aW5tbzI0eDctZGV2LW9ubHktdG9rZW4ta2V5LTAwMDE=", "development key"),
        ("TOKEN_ENCRYPTION_KEY", "c2hvcnQ=", "32 bytes"),
        ("META_APP_SECRET", "dev-app-secret", "META_APP_SECRET"),
    ],
)
def test_production_rejects_development_messaging_values(
    monkeypatch, name: str, value: str, message: str
) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=message):
        get_settings()


# --- Day 7B: database, pools and the rehearsal ------------------------------------------------


def test_the_transaction_pooler_is_refused_everywhere(monkeypatch) -> None:
    pooler = (
        "postgresql+psycopg://postgres.ref:pw@aws-0-sa-east-1.pooler.supabase.com:6543/postgres"
    )
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", pooler)

    with pytest.raises(ConfigurationError, match="session pooler on port 5432"):
        get_settings()


def test_production_refuses_the_transaction_pooler(monkeypatch) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres.ref:pw@aws-0-sa-east-1.pooler.supabase.com:6543/postgres",
    )

    with pytest.raises(ConfigurationError, match="6543"):
        get_settings()


def test_production_accepts_the_session_pooler(monkeypatch) -> None:
    _complete_production_env(monkeypatch)
    url = (
        "postgresql+psycopg://postgres.ref:pw@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
        "?sslmode=require"
    )
    monkeypatch.setenv("DATABASE_URL", url)

    assert get_settings().database_url == url


def test_pool_sizes_have_small_defaults_and_can_be_set(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("DB_MAX_OVERFLOW", raising=False)
    assert (get_settings().db_pool_size, get_settings().db_max_overflow) == (5, 1)

    get_settings.cache_clear()
    monkeypatch.setenv("DB_POOL_SIZE", "8")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    assert (get_settings().db_pool_size, get_settings().db_max_overflow) == (8, 0)

    get_settings.cache_clear()
    monkeypatch.setenv("DB_POOL_SIZE", "0")
    with pytest.raises(ConfigurationError, match="DB_POOL_SIZE"):
        get_settings()


def test_the_worker_needs_a_connection_per_job_thread(monkeypatch) -> None:
    from inmo24x7_api.worker import check_pool

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("WORKER_CONCURRENCY", "4")
    monkeypatch.setenv("DB_POOL_SIZE", "3")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "1")
    with pytest.raises(ConfigurationError, match="WORKER_CONCURRENCY"):
        check_pool(get_settings())

    get_settings.cache_clear()
    monkeypatch.setenv("DB_POOL_SIZE", "5")
    monkeypatch.setenv("DB_MAX_OVERFLOW", "0")
    check_pool(get_settings())


def test_production_refuses_the_fake_model_and_log_sender_outside_the_rehearsal(
    monkeypatch,
) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.delenv("LLM_MODEL")
    with pytest.raises(ConfigurationError, match="LLM_MODEL"):
        get_settings()

    get_settings.cache_clear()
    monkeypatch.setenv("REHEARSAL", "true")
    monkeypatch.setenv("WHATSAPP_SENDER", "log")
    settings = get_settings()
    assert (settings.rehearsal, settings.llm_model, settings.whatsapp_sender) == (True, "", "log")


def test_the_rehearsal_flag_still_refuses_dev_auth(monkeypatch) -> None:
    _complete_production_env(monkeypatch)
    monkeypatch.setenv("REHEARSAL", "true")
    monkeypatch.setenv("AUTH_MODE", "dev")

    with pytest.raises(ConfigurationError, match="AUTH_MODE=dev"):
        get_settings()


def test_the_rehearsal_flag_is_only_for_production(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("REHEARSAL", "true")

    with pytest.raises(ConfigurationError, match="REHEARSAL"):
        get_settings()


def test_the_production_env_example_never_enables_the_rehearsal() -> None:
    from pathlib import Path

    example = Path(__file__).resolve().parents[4] / "deploy" / ".env.production.example"
    names = {
        line.split("=", 1)[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    assert "REHEARSAL" not in names
    assert {"APP_ENV", "DATABASE_URL", "SUPABASE_JWKS_URL", "SUPABASE_SERVICE_ROLE_KEY"} <= names
    assert ":6543/" not in example.read_text(encoding="utf-8")


MONITORING = (
    "SENTRY_DSN",
    "SENTRY_TRACES_SAMPLE_RATE",
    "SENTRY_API_TOKEN",
    "SENTRY_ORG",
    "SENTRY_PROJECTS",
    "SENTRY_API_URL",
    "GRAFANA_URL",
    "LOKI_DATASOURCE",
    "LLM_MONTHLY_COST_ALERT_USD",
)


def test_production_runs_without_any_monitoring_setting(monkeypatch) -> None:
    _production_env(
        monkeypatch, database_url="postgresql+psycopg://db/app", cors="https://app.example.com"
    )
    for name in MONITORING:
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert (settings.sentry_dsn, settings.sentry_traces_sample_rate) == ("", 0.0)
    assert (settings.sentry_api_token, settings.sentry_org, dict(settings.sentry_projects)) == (
        "",
        "",
        {},
    )
    assert settings.sentry_api_url == "https://sentry.io"
    assert (settings.grafana_url, settings.loki_datasource) == ("", "loki")
    assert settings.llm_monthly_cost_alert_usd is None


def test_monitoring_settings_are_read(monkeypatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://key@o1.ingest.us.sentry.io/2")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")
    monkeypatch.setenv(
        "SENTRY_PROJECTS", "api=inmo24x7-api, panel=inmo24x7-panel,backoffice=inmo24x7-bo"
    )
    monkeypatch.setenv("SENTRY_API_URL", "https://de.sentry.io/")
    monkeypatch.setenv("GRAFANA_URL", "https://grafana.example.com/")
    monkeypatch.setenv("LLM_MONTHLY_COST_ALERT_USD", "25.50")

    settings = get_settings()

    assert settings.sentry_traces_sample_rate == 0.1
    assert dict(settings.sentry_projects) == {
        "api": "inmo24x7-api",
        "panel": "inmo24x7-panel",
        "backoffice": "inmo24x7-bo",
    }
    assert settings.sentry_api_url == "https://de.sentry.io"
    assert settings.grafana_url == "https://grafana.example.com"
    assert str(settings.llm_monthly_cost_alert_usd) == "25.50"


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("SENTRY_TRACES_SAMPLE_RATE", "2", "between 0 and 1"),
        ("SENTRY_TRACES_SAMPLE_RATE", "mucho", "must be a number"),
        ("SENTRY_PROJECTS", "worker=inmo24x7-worker", "SENTRY_PROJECTS"),
        ("SENTRY_PROJECTS", "api=", "SENTRY_PROJECTS"),
        ("LLM_MONTHLY_COST_ALERT_USD", "veinte", "USD"),
        ("LLM_MONTHLY_COST_ALERT_USD", "0", "greater than zero"),
    ],
)
def test_bad_monitoring_values_stop_startup(
    monkeypatch, name: str, value: str, message: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError, match=message):
        get_settings()
