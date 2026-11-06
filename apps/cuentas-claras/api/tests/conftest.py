import os

# No test may send anything to LangSmith or Sentry, whatever the environment says.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["SENTRY_DSN"] = ""
import re
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from cuentas_claras_api.container import create_business_use_case, get_token_verifier
from cuentas_claras_api.database import get_session
from cuentas_claras_api.main import app
from fastapi.testclient import TestClient
from followup_core.identity.domain.token_verifier import VerifiedToken
from followup_core.identity.infrastructure.supabase_verifier import FakeTokenVerifier
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[4]
SAMPLES = ROOT / "docs/samples/cuentas-claras"
DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://followup:followup@localhost:5433/followup_test"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
_DATABASE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    name = parsed.database
    if not name or not _DATABASE_NAME.fullmatch(name):
        raise RuntimeError("TEST_DATABASE_URL must include a valid database name.")
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            if not connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ):
                connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def test_engine():
    _ensure_database(TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def database(test_engine):
    """A fresh schema per test: every branch migrated (`alembic upgrade heads`)."""
    with test_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    test_engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "heads")
    yield test_engine


@pytest.fixture
def sessions(database) -> sessionmaker[Session]:
    return sessionmaker(bind=database, autoflush=False, expire_on_commit=False)


@pytest.fixture
def client(sessions) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        session = sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    verifier = FakeTokenVerifier()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_token_verifier] = lambda: verifier
    app.state.test_verifier = verifier
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def invite(email: str, name: str, business_type: str = "mantenimiento") -> UUID:
    """An admin's "Dar de alta" for this email (sign-up is invitation-only), on a session of
    the test client's own database."""
    session_scope = app.dependency_overrides[get_session]()
    session = next(session_scope)
    tenant = create_business_use_case(session).execute(uuid4(), name, business_type, email)
    next(session_scope, None)  # commits
    return tenant.id


class Owner:
    """A signed-up Cuentas Claras business and its owner (dev-style token)."""

    def __init__(
        self, client: TestClient, name: str = "Ascensores Delta", user_id: UUID | None = None
    ) -> None:
        self.client = client
        self.user_id = user_id or uuid4()
        self.email = f"{self.user_id}@example.com"
        token = f"tok-{self.user_id}"
        app.state.test_verifier.register(token, VerifiedToken(self.user_id, self.email))
        self.headers = {"Authorization": f"Bearer {token}"}
        invite(self.email, name)
        response = client.post("/me/sign-up", headers=self.headers)
        assert response.status_code == 201, response.json()
        body = response.json()
        self.tenant_id = UUID(body["tenant"]["id"])
        self.profile_id = UUID(body["profile"]["id"])

    def get(self, path: str, **kwargs):
        return self.client.get(path, headers=self.headers, **kwargs)

    def post(self, path: str, body: dict | None = None, **kwargs):
        return self.client.post(path, json=body, headers=self.headers, **kwargs)

    def patch(self, path: str, body: dict):
        return self.client.patch(path, json=body, headers=self.headers)

    def upload(self, path: str, file_name: str, content: bytes):
        return self.client.post(path, files={"file": (file_name, content)}, headers=self.headers)

    def import_sample(self, name: str = "facturas.csv"):
        return self.upload("/invoices/import", name, (SAMPLES / name).read_bytes())


@pytest.fixture
def owner(client: TestClient) -> Owner:
    return Owner(client)


def make_admin(sessions, profile_id: UUID) -> None:
    with sessions() as session:
        session.execute(
            text("UPDATE profiles SET is_platform_admin = true WHERE id = :id"), {"id": profile_id}
        )
        session.commit()
