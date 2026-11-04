from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

settings = get_settings()
# Small pools: Supabase's session pooler gives each client connection a server connection,
# and the plan caps them (docs/go-live.md has the math). The worker raises its pool to fit
# WORKER_CONCURRENCY through its own environment.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
# LLM usage rows are written outside the turn's transaction, while the turn still holds its
# connection: one extra connection per process, and a short wait (a slow write is dropped
# and logged, never a slow turn).
usage_engine = create_engine(
    settings.database_url, pool_pre_ping=True, pool_size=1, max_overflow=0, pool_timeout=3
)
UsageSessionLocal = sessionmaker(bind=usage_engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
