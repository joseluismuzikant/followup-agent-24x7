import os
import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from followup_core.infrastructure.db import Base
from inmo24x7_api.database import get_session
from inmo24x7_api.main import app
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

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


@pytest.fixture
def database(test_engine):
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)


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
