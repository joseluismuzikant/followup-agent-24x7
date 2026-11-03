import os
from dataclasses import dataclass
from functools import lru_cache

from followup_core.conversation.infrastructure.llm_providers import parse_model_spec
from followup_core.messaging.infrastructure.crypto import TokenCipherError, parse_key

DEFAULT_DATABASE_URL = "postgresql+psycopg://followup:followup@localhost:5433/followup"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:5174"
DEFAULT_LLM_TIMEOUT_SECONDS = 20.0
DEFAULT_SIMULATOR_DAILY_LIMIT = 300
AUTH_MODES = ("supabase", "dev")
WHATSAPP_SENDERS = ("cloud", "log")
# Committed in .env.example for local development only: production refuses it.
DEV_TOKEN_ENCRYPTION_KEY = "aW5tbzI0eDctZGV2LW9ubHktdG9rZW4ta2V5LTAwMDE="
DEV_META_APP_SECRET = "dev-app-secret"
DEV_WHATSAPP_VERIFY_TOKEN = "dev-verify-token"
DEFAULT_GRAPH_BASE_URL = "https://graph.facebook.com"
# The latest Graph API version when Day 5 was built (v26.0, July 2026).
DEFAULT_GRAPH_API_VERSION = "v26.0"
DEFAULT_PANEL_URL = "http://localhost:5173"


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    database_url: str
    cors_origins: tuple[str, ...]
    version: str
    commit: str
    build_date: str
    supabase_url: str
    supabase_jwt_secret: str
    supabase_jwks_url: str
    auth_mode: str = "supabase"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    simulator_daily_limit: int = DEFAULT_SIMULATOR_DAILY_LIMIT
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = ""
    # A LangSmith agent address (agent id + environment) replaces the project when set.
    langsmith_agent_id: str = ""
    langsmith_agent_environment: str = ""
    langsmith_endpoint: str = ""
    langsmith_redact_pii: bool = True
    langsmith_ui_url: str = ""
    # WhatsApp Cloud API
    meta_app_secret: str = DEV_META_APP_SECRET
    whatsapp_verify_token: str = DEV_WHATSAPP_VERIFY_TOKEN
    meta_graph_base_url: str = DEFAULT_GRAPH_BASE_URL
    meta_graph_api_version: str = DEFAULT_GRAPH_API_VERSION
    whatsapp_sender: str = "log"
    whatsapp_default_template: str = "hello_world"
    whatsapp_default_template_language: str = "en_US"
    token_encryption_key: str = DEV_TOKEN_ENCRYPTION_KEY
    inbound_debounce_seconds: float = 3.0
    worker_concurrency: int = 4
    # New-lead email
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False
    email_from: str = "inmo24x7 <avisos@inmo24x7.local>"
    panel_url: str = DEFAULT_PANEL_URL

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set when APP_ENV=production.")
    return value


def _positive_number(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a number.") from error
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero.")
    return value


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _llm_settings(production: bool) -> tuple[str, str]:
    """LLM_MODEL and the API key of its provider. Empty model = fake LLM (development only)."""
    model = os.getenv("LLM_MODEL", "").strip()
    if not model:
        if production:
            raise ConfigurationError("LLM_MODEL must be set when APP_ENV=production.")
        return "", ""
    try:
        provider, _ = parse_model_spec(model)
    except ValueError as error:
        raise ConfigurationError(str(error)) from error
    api_key = os.getenv(provider.api_key_env, "").strip()
    if not api_key:
        raise ConfigurationError(f"{provider.api_key_env} must be set for LLM_MODEL={model}.")
    return model, api_key


def _auth_mode(production: bool) -> str:
    """AUTH_MODE: Supabase JWTs, or `dev:<email>` tokens for local development only."""
    mode = os.getenv("AUTH_MODE", "").strip().lower() or ("supabase" if production else "dev")
    if mode not in AUTH_MODES:
        raise ConfigurationError("AUTH_MODE must be 'supabase' or 'dev'.")
    if production and mode == "dev":
        raise ConfigurationError("AUTH_MODE=dev is not allowed when APP_ENV=production.")
    return mode


def _encryption_key(production: bool) -> str:
    value = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
    if production:
        if not value:
            raise ConfigurationError("TOKEN_ENCRYPTION_KEY must be set when APP_ENV=production.")
        if value == DEV_TOKEN_ENCRYPTION_KEY:
            raise ConfigurationError("TOKEN_ENCRYPTION_KEY is the development key; generate one.")
    value = value or DEV_TOKEN_ENCRYPTION_KEY
    try:
        parse_key(value)
    except TokenCipherError as error:
        raise ConfigurationError(f"TOKEN_ENCRYPTION_KEY: {error}") from error
    return value


def _messaging_settings(production: bool) -> dict[str, object]:
    def setting(name: str, dev_default: str) -> str:
        value = os.getenv(name, "").strip()
        if production and (not value or value == dev_default):
            raise ConfigurationError(f"{name} must be set when APP_ENV=production.")
        return value or dev_default

    sender = os.getenv("WHATSAPP_SENDER", "").strip().lower() or ("cloud" if production else "log")
    if sender not in WHATSAPP_SENDERS:
        raise ConfigurationError("WHATSAPP_SENDER must be 'cloud' or 'log'.")
    if production and sender != "cloud":
        raise ConfigurationError("WHATSAPP_SENDER must be 'cloud' when APP_ENV=production.")
    return {
        "meta_app_secret": setting("META_APP_SECRET", DEV_META_APP_SECRET),
        "whatsapp_verify_token": setting("WHATSAPP_VERIFY_TOKEN", DEV_WHATSAPP_VERIFY_TOKEN),
        "meta_graph_base_url": os.getenv("META_GRAPH_BASE_URL", "").strip().rstrip("/")
        or DEFAULT_GRAPH_BASE_URL,
        "meta_graph_api_version": os.getenv("META_GRAPH_API_VERSION", "").strip()
        or DEFAULT_GRAPH_API_VERSION,
        "whatsapp_sender": sender,
        "whatsapp_default_template": os.getenv("WHATSAPP_DEFAULT_TEMPLATE", "").strip()
        or "hello_world",
        "whatsapp_default_template_language": os.getenv(
            "WHATSAPP_DEFAULT_TEMPLATE_LANGUAGE", ""
        ).strip()
        or "en_US",
        "token_encryption_key": _encryption_key(production),
        "inbound_debounce_seconds": _non_negative("INBOUND_DEBOUNCE_SECONDS", 3.0),
        "worker_concurrency": int(_positive_number("WORKER_CONCURRENCY", 4)),
    }


def _email_settings(production: bool) -> dict[str, object]:
    def required(name: str, dev_default: str) -> str:
        value = os.getenv(name, "").strip()
        if production and not value:
            raise ConfigurationError(f"{name} must be set when APP_ENV=production.")
        return value or dev_default

    return {
        "smtp_host": required("SMTP_HOST", "localhost"),
        "smtp_port": int(_positive_number("SMTP_PORT", 587 if production else 1025)),
        "smtp_username": os.getenv("SMTP_USERNAME", "").strip(),
        "smtp_password": os.getenv("SMTP_PASSWORD", ""),
        "smtp_starttls": _flag("SMTP_STARTTLS", default=production),
        "email_from": required("EMAIL_FROM", "inmo24x7 <avisos@inmo24x7.local>"),
        "panel_url": required("PANEL_URL", DEFAULT_PANEL_URL).rstrip("/"),
    }


def _non_negative(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be a number.") from error
    if value < 0:
        raise ConfigurationError(f"{name} cannot be negative.")
    return value


@lru_cache
def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "production"}:
        raise ConfigurationError("APP_ENV must be 'development' or 'production'.")

    auth_mode = _auth_mode(app_env == "production")
    if app_env == "production":
        database_url = _required("DATABASE_URL")
        raw_origins = _required("CORS_ORIGINS")
        supabase_url = _required("SUPABASE_URL")
        supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "").strip()
        supabase_jwks_url = os.getenv("SUPABASE_JWKS_URL", "").strip()
        if not supabase_jwt_secret and not supabase_jwks_url:
            raise ConfigurationError(
                "SUPABASE_JWT_SECRET or SUPABASE_JWKS_URL must be set when APP_ENV=production."
            )
    else:
        database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        raw_origins = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
        supabase_jwks_url = os.getenv("SUPABASE_JWKS_URL", "")
        if auth_mode == "supabase" and not supabase_jwt_secret and not supabase_jwks_url:
            raise ConfigurationError(
                "AUTH_MODE=supabase needs SUPABASE_JWT_SECRET or SUPABASE_JWKS_URL "
                "(or use AUTH_MODE=dev locally)."
            )

    llm_model, llm_api_key = _llm_settings(app_env == "production")

    return Settings(
        app_env=app_env,
        database_url=database_url,
        cors_origins=tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip()),
        version=os.getenv("APP_VERSION", "0.1.0"),
        commit=os.getenv("GIT_COMMIT", "unknown"),
        build_date=os.getenv("BUILD_DATE", "unknown"),
        supabase_url=supabase_url,
        supabase_jwt_secret=supabase_jwt_secret,
        supabase_jwks_url=supabase_jwks_url,
        auth_mode=auth_mode,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
        llm_timeout_seconds=_positive_number("LLM_TIMEOUT_SECONDS", DEFAULT_LLM_TIMEOUT_SECONDS),
        simulator_daily_limit=int(
            _positive_number("SIMULATOR_DAILY_LIMIT", DEFAULT_SIMULATOR_DAILY_LIMIT)
        ),
        # LangSmith is optional everywhere, production included.
        langsmith_tracing=_flag("LANGSMITH_TRACING", default=False),
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY", "").strip(),
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "").strip(),
        langsmith_agent_id=os.getenv("LANGSMITH_AGENT_ID", "").strip(),
        langsmith_agent_environment=os.getenv("LANGSMITH_AGENT_ENVIRONMENT", "").strip(),
        langsmith_endpoint=os.getenv("LANGSMITH_ENDPOINT", "").strip(),
        langsmith_redact_pii=_flag("LANGSMITH_REDACT_PII", default=True),
        langsmith_ui_url=os.getenv("LANGSMITH_UI_URL", "").strip().rstrip("/"),
        **_messaging_settings(app_env == "production"),  # type: ignore[arg-type]
        **_email_settings(app_env == "production"),  # type: ignore[arg-type]
    )
