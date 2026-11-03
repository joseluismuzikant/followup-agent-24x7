"""The dev seed: real use cases, idempotent, and never against production or a remote DB."""

import sys
from pathlib import Path

import pytest
from followup_core.identity.infrastructure.dev_verifier import dev_user_id
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts"))

import seed_dev  # noqa: E402

TABLES = (
    "tenants",
    "profiles",
    "tenant_onboarding",
    "tenant_settings",
    "agent_config_versions",
    "properties",
    "property_imports",
    "whatsapp_connections",
)


def _snapshot(session) -> dict[str, object]:
    counts = {
        table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar() for table in TABLES
    }
    counts["properties_updated"] = session.execute(
        text("SELECT max(updated_at) FROM properties")
    ).scalar()
    return counts


def test_seed_creates_the_dev_accounts_and_running_it_twice_changes_nothing(db_session) -> None:
    seed_dev.seed(db_session)
    first = _snapshot(db_session)

    seed_dev.seed(db_session)

    assert _snapshot(db_session) == first
    assert first["tenants"] == 2 and first["profiles"] == 2
    assert first["properties"] == 20 and first["property_imports"] == 1
    assert first["whatsapp_connections"] == 1
    admin = db_session.execute(
        text("SELECT id, is_platform_admin FROM profiles WHERE email = 'admin@local.test'")
    ).one()
    assert admin == (dev_user_id("admin@local.test"), True)
    onboarding = db_session.execute(
        text(
            "SELECT o.finished_at IS NOT NULL FROM tenant_onboarding o "
            "JOIN profiles p ON p.tenant_id = o.tenant_id "
            "WHERE p.email = 'dueno@inmobiliariasur.test'"
        )
    ).scalar()
    assert onboarding is True
    assert (
        db_session.execute(
            text("SELECT count(*) FROM profiles WHERE email = 'nuevo@local.test'")
        ).scalar()
        == 0
    )


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@db.supabase.co:5432/postgres",
        "postgresql+psycopg://u:p@10.0.0.5:5432/followup",
        "postgresql+psycopg://u:p@db:5432/followup",
    ],
)
def test_reset_refuses_a_non_local_database(url: str) -> None:
    with pytest.raises(seed_dev.SeedError, match="local database"):
        seed_dev.reset_database(url)


def test_reset_refuses_from_the_command_line_too(monkeypatch, capsys) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@prod.example.com/app")
    from inmo24x7_api.config import get_settings

    get_settings.cache_clear()
    try:
        assert seed_dev.main(["--reset", "--yes"]) == 2
    finally:
        get_settings.cache_clear()
    assert "local database" in capsys.readouterr().err


def test_the_seed_refuses_production(monkeypatch, capsys) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    assert seed_dev.main([]) == 2
    assert "APP_ENV=production" in capsys.readouterr().err
