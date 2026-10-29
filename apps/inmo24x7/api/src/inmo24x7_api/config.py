import os
from dataclasses import dataclass
from functools import lru_cache

from followup_core.conversation.infrastructure.llm_providers import parse_model_spec

DEFAULT_DATABASE_URL = "postgresql+psycopg://followup:followup@localhost:5433/followup"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:5174"
DEFAULT_LLM_TIMEOUT_SECONDS = 20.0
DEFAULT_SIMULATOR_DAILY_LIMIT = 300


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
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    simulator_daily_limit: int = DEFAULT_SIMULATOR_DAILY_LIMIT
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = ""
    langsmith_endpoint: str = ""
    langsmith_redact_pii: bool = True
    langsmith_ui_url: str = ""

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


@lru_cache
def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "production"}:
        raise ConfigurationError("APP_ENV must be 'development' or 'production'.")

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
        langsmith_endpoint=os.getenv("LANGSMITH_ENDPOINT", "").strip(),
        langsmith_redact_pii=_flag("LANGSMITH_REDACT_PII", default=True),
        langsmith_ui_url=os.getenv("LANGSMITH_UI_URL", "").strip().rstrip("/"),
    )
