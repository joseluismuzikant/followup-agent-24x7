import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_DATABASE_URL = "postgresql+psycopg://followup:followup@localhost:5433/followup"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://localhost:5174"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    raw_origins = os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return Settings(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        cors_origins=tuple(origin.strip() for origin in raw_origins.split(",") if origin.strip()),
    )
