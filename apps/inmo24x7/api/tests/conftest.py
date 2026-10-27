import os
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from followup_core.identity.domain.token_verifier import VerifiedToken
from followup_core.identity.infrastructure.supabase_verifier import FakeTokenVerifier
from inmo24x7_api.container import get_token_verifier
from inmo24x7_api.database import get_session
from inmo24x7_api.main import app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://followup:followup@localhost:5433/followup_test"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
_DATABASE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def ensure_database(url: str) -> None:
    parsed = make_url(url)
    database_name = parsed.database
    if not database_name or not _DATABASE_NAME.fullmatch(database_name):
        raise RuntimeError("TEST_DATABASE_URL must include a valid database name.")

    admin_engine = create_engine(
        parsed.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            )
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def test_engine():
    ensure_database(TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


def migrate_database(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        TEST_DATABASE_URL.replace("%", "%%"),
    )
    command.upgrade(config, "head")


@pytest.fixture
def database(test_engine):
    migrate_database(test_engine)
    yield test_engine


@pytest.fixture
def db_session(database):
    session = sessionmaker(bind=database, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()


@pytest.fixture
def client(database) -> Iterator[TestClient]:
    testing_session = sessionmaker(bind=database, autoflush=False, expire_on_commit=False)

    def override_session() -> Iterator[Session]:
        session = testing_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def fake_verifier(client) -> Iterator[FakeTokenVerifier]:
    verifier = FakeTokenVerifier()
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    yield verifier
    app.dependency_overrides.pop(get_token_verifier, None)


@pytest.fixture
def auth(fake_verifier, db_session):
    class AuthHelper:
        @staticmethod
        def register(user_id: UUID, email: str = "a@example.com") -> str:
            token = f"tok-{user_id}"
            fake_verifier.register(token, VerifiedToken(user_id=user_id, email=email))
            return token

        @staticmethod
        def make_admin(user_id: UUID) -> None:
            db_session.execute(
                text("UPDATE profiles SET is_platform_admin = true WHERE id = :id"),
                {"id": user_id},
            )
            db_session.commit()

    return AuthHelper()
