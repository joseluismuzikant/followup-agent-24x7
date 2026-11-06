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
    "leads",
    "visits",
    "conversation_messages",
    "whatsapp_outbound",
    "audit_events",
    "tenant_owner_claims",
    "accounts",
    "invitations",
    "dev_passwords",
    "cc_clients",
    "cc_invoices",
    "cc_invoice_imports",
)


def _snapshot(session) -> dict[str, object]:
    counts = {
        table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar() for table in TABLES
    }
    counts["properties_updated"] = session.execute(
        text("SELECT max(updated_at) FROM properties")
    ).scalar()
    for product in ("inmo24x7", "cuentas_claras"):
        for table in ("tenants", "profiles"):
            counts[f"{product}_{table}"] = session.execute(
                text(f"SELECT count(*) FROM {table} WHERE product = :product"),
                {"product": product},
            ).scalar()
    return counts


def test_seed_creates_the_dev_accounts_and_running_it_twice_changes_nothing(db_session) -> None:
    seed_dev.seed(db_session)
    first = _snapshot(db_session)

    seed_dev.seed(db_session)

    assert _snapshot(db_session) == first
    # Plataforma, Inmobiliaria Sur, the five S8 businesses and Nuevo Inmo; two wait for
    # their invited owners.
    assert first["inmo24x7_tenants"] == 8 and first["inmo24x7_profiles"] == 6
    assert first["properties"] == 60 and first["property_imports"] == 3
    assert first["whatsapp_connections"] == 3
    # Every business was created by an admin ("Dar de alta"), in both products.
    assert first["tenant_owner_claims"] == 14
    # One account per person; the three invited ones still have the temporary password.
    assert first["accounts"] == first["dev_passwords"] == 12
    assert first["invitations"] == 4
    must_change = db_session.execute(
        text("SELECT email FROM accounts WHERE must_change_password ORDER BY email")
    ).scalars()
    assert list(must_change) == [
        "invitada@villaurquiza.test",
        "invitado@matafuegosnorte.test",
        "nuevo@local.test",
    ]
    admin = db_session.execute(
        text(
            "SELECT id, is_platform_admin FROM profiles "
            "WHERE email = 'admin@local.test' AND product = 'inmo24x7'"
        )
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


def test_the_seed_gives_cuentas_claras_its_own_accounts(db_session) -> None:
    seed_dev.seed(db_session)

    first = _snapshot(db_session)
    # Plataforma, Ascensores Delta, Monitoreo Sur (suspended), Soporte IT Norte (wizard
    # unfinished), and Nuevo Negocio and Matafuegos Norte (invited); admin@local.test is a
    # second profile of the same user.
    assert first["cuentas_claras_tenants"] == 6 and first["cuentas_claras_profiles"] == 4
    states = dict(
        db_session.execute(
            text(
                "SELECT t.name, t.status || '/' || o.current_step FROM tenants t "
                "JOIN tenant_onboarding o ON o.tenant_id = t.id "
                "WHERE t.product = 'cuentas_claras'"
            )
        ).all()
    )
    assert states["Monitoreo Sur"].startswith("suspended/")
    assert states["Soporte IT Norte"] == "active/invoices"
    assert first["cc_invoices"] == 40 and first["cc_clients"] == 25
    assert first["cc_invoice_imports"] == 1
    admin = db_session.execute(
        text(
            "SELECT id, user_id, is_platform_admin FROM profiles "
            "WHERE email = 'admin@local.test' AND product = 'cuentas_claras'"
        )
    ).one()
    assert admin.user_id == dev_user_id("admin@local.test")
    assert admin.id != admin.user_id and admin.is_platform_admin
    finished = db_session.execute(
        text(
            "SELECT o.current_step, o.finished_at IS NOT NULL FROM tenant_onboarding o "
            "JOIN tenants t ON t.id = o.tenant_id "
            "WHERE t.product = 'cuentas_claras' AND t.name = 'Ascensores Delta'"
        )
    ).one()
    assert tuple(finished) == ("done", True)


def test_the_sample_invoices_are_shifted_to_today() -> None:
    from datetime import date

    rows = seed_dev.shifted_invoices(date(2026, 11, 12)).decode().splitlines()
    original = seed_dev.SAMPLE_INVOICES.read_text(encoding="utf-8").splitlines()

    assert rows[0] == original[0] and len(rows) == len(original)
    # 10 days after the reference date: every date moves 10 days, nothing else changes.
    assert "23/09/2026;" in original[1] and "03/10/2026;" in rows[1]
    assert rows[1].split(";")[:9] == original[1].split(";")[:9]


def test_the_seed_fills_the_inbox_through_the_pipeline(db_session) -> None:
    seed_dev.seed(db_session)

    statuses = dict(
        db_session.execute(
            text("SELECT status, count(*) FROM leads WHERE NOT is_test GROUP BY status")
        ).all()
    )
    assert statuses == {
        "visit_proposed": 2,
        "visit_confirmed": 1,
        "human_requested": 2,
        "qualifying": 3,
    }
    # Contacts come from the WhatsApp number; replies went through the log sender.
    assert (
        db_session.execute(text("SELECT count(*) FROM leads WHERE contact IS NULL")).scalar() == 0
    )
    assert db_session.execute(
        text("SELECT DISTINCT status FROM whatsapp_outbound")
    ).scalars().all() == ["read"]
    confirmations = db_session.execute(
        text("SELECT count(*) FROM conversation_messages WHERE text LIKE '%confirmó la visita'")
    ).scalar()
    assert confirmations == 1
    # Two leads wrote at 23:10 (out of hours) and two are older than 24 hours.
    out_of_hours = db_session.execute(
        text(
            "SELECT count(*) FROM leads WHERE "
            "to_char(created_at AT TIME ZONE 'America/Argentina/Buenos_Aires', 'HH24:MI') "
            "BETWEEN '23:10' AND '23:20'"
        )
    ).scalar()
    assert out_of_hours == 2
    stale = db_session.execute(
        text("SELECT count(*) FROM leads WHERE last_activity_at < now() - interval '24 hours'")
    ).scalar()
    assert stale >= 2
    named = db_session.execute(
        text("SELECT count(*) FROM leads WHERE status = 'human_requested' AND visitor_name IS NULL")
    ).scalar()
    assert named == 0
    qualified = db_session.execute(
        text("SELECT count(*) FROM leads WHERE answers ?& array['operation', 'zone', 'budget']")
    ).scalar()
    assert qualified >= 2


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


def test_the_seed_gives_the_backoffice_one_business_per_state(db_session) -> None:
    from datetime import UTC, datetime

    from inmo24x7_api.backoffice.domain.rules import needs_help, whatsapp_badge
    from inmo24x7_api.backoffice.infrastructure.queries import SqlAlchemyBackofficeQueries

    seed_dev.seed(db_session)
    now = datetime.now(UTC)
    rows = {row.name: row for row in SqlAlchemyBackofficeQueries(db_session).tenants(now)}

    def badge(name: str) -> str:
        return whatsapp_badge(rows[name].whatsapp_status, rows[name].business_verification).value

    assert badge("Inmobiliaria Sur") == "connected"
    assert badge("Palermo Propiedades") == "verification_pending"
    assert badge("Caballito Inmuebles") == "action_required"
    assert badge("Belgrano Hogar") == "not_connected"
    assert rows["Belgrano Hogar"].onboarding.done == 2
    assert needs_help(rows["Belgrano Hogar"], now) and needs_help(rows["Caballito Inmuebles"], now)
    assert rows["Norte Bienes Raíces"].suspended
    assert rows["Villa Urquiza Propiedades"].owner_pending
    failing = db_session.execute(
        text(
            "SELECT w.last_error_code, w.failing_since < now() - interval '25 hours' "
            "FROM whatsapp_connections w JOIN tenants t ON t.id = w.tenant_id "
            "WHERE t.name = 'Caballito Inmuebles'"
        )
    ).one()
    assert tuple(failing) == ("190", True)
    actions = {
        row.action for row in db_session.execute(text("SELECT DISTINCT action FROM audit_events"))
    }
    assert {
        "owner_claimed",
        "owner_invited",
        "whatsapp_error",
        "tenant_suspended",
        "tenant_created_by_admin",
    } <= actions
