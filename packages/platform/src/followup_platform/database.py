"""Engines and the request session of a product API."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .settings import Settings


@dataclass(frozen=True, slots=True)
class Database:
    engine: Engine
    sessions: sessionmaker[Session]
    # LLM usage rows are written outside the turn's transaction, while the turn still holds
    # its connection: one extra connection per process, and a short wait (a slow write is
    # dropped and logged, never a slow turn).
    usage_engine: Engine
    usage_sessions: sessionmaker[Session]


def build_database(settings: Settings) -> Database:
    # Small pools: Supabase's session pooler gives each client connection a server
    # connection, and the plan caps them (docs/go-live.md has the math). The worker raises
    # its pool to fit WORKER_CONCURRENCY through its own environment.
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )
    usage_engine = create_engine(
        settings.database_url, pool_pre_ping=True, pool_size=1, max_overflow=0, pool_timeout=3
    )
    return Database(
        engine=engine,
        sessions=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        usage_engine=usage_engine,
        usage_sessions=sessionmaker(bind=usage_engine, autoflush=False, expire_on_commit=False),
    )


def session_dependency(sessions: Callable[[], Session]) -> Callable[[], Iterator[Session]]:
    """The FastAPI dependency: one session per request, committed when the endpoint returns
    and rolled back when it raises."""

    def get_session() -> Iterator[Session]:
        session = sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return get_session
