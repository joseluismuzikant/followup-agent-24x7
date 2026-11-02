"""Seed the local development database (AUTH_MODE=dev).

    uv run --all-packages python scripts/seed_dev.py            # seed (idempotent)
    uv run --all-packages python scripts/seed_dev.py --reset    # drop everything, migrate, seed

Everything goes through the real use cases (sign-up, agent setup, onboarding, property
import), so the seed stays valid as the domain changes. Refuses to run with
APP_ENV=production, and --reset only touches a database on localhost.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

from _cli import ROOT, load_env_file

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SAMPLE_PROPERTIES = ROOT / "docs" / "samples" / "propiedades.csv"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


@dataclass(frozen=True)
class DevAccount:
    email: str
    business: str | None
    what: str


ADMIN = DevAccount("admin@local.test", "Plataforma", "administrador de la plataforma (backoffice)")
OWNER = DevAccount(
    "dueno@inmobiliariasur.test",
    "Inmobiliaria Sur",
    "dueño de Inmobiliaria Sur, configurada y con 20 propiedades",
)
NEW = DevAccount("nuevo@local.test", None, "sin cuenta: para probar el alta y el asistente")
ACCOUNTS = (ADMIN, OWNER, NEW)


class SeedError(RuntimeError):
    pass


def refuse_production() -> None:
    if os.getenv("APP_ENV", "development").strip().lower() == "production":
        raise SeedError("seed_dev.py never runs with APP_ENV=production.")


def require_local(database_url: str) -> None:
    from sqlalchemy.engine import make_url

    host = make_url(database_url).host or ""
    if host not in LOCAL_HOSTS:
        raise SeedError(
            f"--reset only works on a local database (localhost or 127.0.0.1), not '{host}'."
        )


def reset_database(database_url: str) -> None:
    """Drops the public schema of the local database and migrates it from scratch."""
    require_local(database_url)
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def _sign_up(session: Session, account: DevAccount):
    from followup_core.identity.infrastructure.dev_verifier import dev_user_id
    from inmo24x7_api.container import sign_up_use_case

    assert account.business is not None
    return sign_up_use_case(session).execute(
        dev_user_id(account.email), account.email, account.business, "inmobiliaria"
    )


def _configure_owner(session: Session, tenant_id, profile_id) -> None:
    from followup_core.tenancy.application.agent_setup import AgentConfigDraft, QuestionDraft
    from followup_core.tenancy.domain.onboarding import OnboardingStep
    from inmo24x7_api.container import (
        advance_onboarding_use_case,
        get_agent_setup_use_case,
        import_properties_use_case,
        save_agent_setup_use_case,
    )
    from inmo24x7_api.properties.infrastructure.repositories import SqlAlchemyPropertyRepository

    setup = get_agent_setup_use_case(session).execute(tenant_id)
    defaults = setup.defaults
    # Saving the defaults again creates no new version (a save only versions changes).
    save_agent_setup_use_case(session).execute(
        tenant_id=tenant_id,
        profile_id=profile_id,
        draft=AgentConfigDraft(
            agent_name=defaults.agent_name,
            tone=defaults.tone,
            after_hours_mode=defaults.after_hours_mode,
            qualification_questions=tuple(
                QuestionDraft(q.key, q.label, q.kind, q.options, q.enabled)
                for q in defaults.qualification_questions
            ),
        ),
        team_hours=setup.team_hours,
        notification_emails=setup.notification_emails,
    )
    # One step at a time, as the wizard does; steps already reached are no-ops.
    advance = advance_onboarding_use_case(session)
    for step in (OnboardingStep.TRY, OnboardingStep.WHATSAPP, OnboardingStep.DONE):
        advance.execute(tenant_id, step)
    if not SqlAlchemyPropertyRepository(session).has_any(tenant_id):
        import_properties_use_case(session).execute(
            tenant_id, profile_id, SAMPLE_PROPERTIES.name, SAMPLE_PROPERTIES.read_bytes()
        )


def seed(session: Session) -> None:
    """Creates the dev accounts; running it again changes nothing."""
    from followup_core.identity.application.set_platform_admin import SetPlatformAdmin
    from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository

    _sign_up(session, ADMIN)
    SetPlatformAdmin(SqlAlchemyProfileRepository(session)).execute(ADMIN.email)
    owner = _sign_up(session, OWNER)
    _configure_owner(session, owner.tenant.id, owner.profile.id)
    session.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the local development database.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate the database")
    parser.add_argument("--yes", action="store_true", help="do not ask before --reset")
    args = parser.parse_args(argv)

    load_env_file(ROOT / ".env")
    try:
        refuse_production()
        from inmo24x7_api.config import get_settings

        database_url = get_settings().database_url
        if args.reset:
            require_local(database_url)
            if not args.yes:
                answer = input("Esto borra TODOS los datos de la base local. ¿Seguir? [s/N] ")
                if answer.strip().lower() not in {"s", "si", "sí", "y", "yes"}:
                    print("Cancelado.")
                    return 1
            reset_database(database_url)

        from inmo24x7_api.database import SessionLocal

        with SessionLocal() as session:
            seed(session)
    except SeedError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print("\nListo. Con AUTH_MODE=dev entrá con cualquiera de estos emails:")
    for account in ACCOUNTS:
        print(f"  {account.email:<30} {account.what}")
    print("\nPanel: http://localhost:5173   Backoffice: http://localhost:5174")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
