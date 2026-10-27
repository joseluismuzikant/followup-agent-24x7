import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_DATABASE_URL = "postgresql+psycopg://followup:followup@localhost:5433/followup"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:5174"


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
    supabase_anon_key: str
    supabase_jwt_secret: str
    supabase_jwks_url: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set when APP_ENV=production.")
    return value


@lru_cache
def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env not in {"development", "production"}:
        raise ConfigurationError("APP_ENV must be 'development' or 'production'.")

    if app_env == "production":
        database_url = _required("DATABASE_URL")
        raw_origins = _required("CORS_ORIGINS")
        supabase_url = _required("SUPABASE_URL")
        supabase_anon_key = _required("SUPABASE_ANON_KEY")
        supabase_jwt_secret = _required("SUPABASE_JWT_SECRET")
    else:
        database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        raw_origins = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_anon_key = os.getenv("SUPABASE_ANON_KEY", "")
        supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")

    return Settings(
        app_env=app_env,
        database_url=database_url,
        cors_origins=tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip()),
        version=os.getenv("APP_VERSION", "0.1.0"),
        commit=os.getenv("GIT_COMMIT", "unknown"),
        build_date=os.getenv("BUILD_DATE", "unknown"),
        supabase_url=supabase_url,
        supabase_anon_key=supabase_anon_key,
        supabase_jwt_secret=supabase_jwt_secret,
        supabase_jwks_url=os.getenv("SUPABASE_JWKS_URL", ""),
    )
