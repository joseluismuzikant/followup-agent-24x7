"""Seed the local development database (AUTH_MODE=dev).

    uv run --all-packages python scripts/seed_dev.py            # seed (idempotent)
    uv run --all-packages python scripts/seed_dev.py --reset    # drop everything, migrate, seed

Everything goes through the real use cases (sign-up, agent setup, onboarding, property
import), so the seed stays valid as the domain changes. The inbox and the dashboard get about
eight WhatsApp leads, created by the real pipeline (signed webhook payloads, worker handlers,
the fake model and the log sender) on a clock set to this week and last week. Refuses to run
with APP_ENV=production, and --reset only touches a database on localhost.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, replace
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

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
    "dueño de Inmobiliaria Sur: 20 propiedades y WhatsApp de prueba (dev-phone-1)",
)
DEV_PHONE_NUMBER_ID = "dev-phone-1"
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
    _connect_whatsapp(session, tenant_id)


def _connect_whatsapp(session: Session, tenant_id) -> None:
    """A fake number with the log sender: scripts/simulate_whatsapp.py talks to it and
    nothing ever reaches Meta."""
    from followup_core.messaging.application.connections import ConnectionDraft
    from followup_core.messaging.domain.connection import SenderKind
    from followup_core.messaging.infrastructure.repositories import (
        SqlAlchemyConnectionRepository,
    )
    from inmo24x7_api.container import get_messaging_services, save_connection_use_case

    if SqlAlchemyConnectionRepository(session).get_by_tenant(tenant_id) is not None:
        return
    save_connection_use_case(session, get_messaging_services()).execute(
        tenant_id,
        ConnectionDraft(
            phone_number_id=DEV_PHONE_NUMBER_ID,
            waba_id="dev-waba-1",
            display_phone_number="+54 9 11 5555-0100",
            access_token="dev-token-not-used-by-the-log-sender",
            sender=SenderKind.LOG,
        ),
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
    seed_inbox(session, owner.tenant.id, owner.profile.id)


# --- Inbox and dashboard ----------------------------------------------------------------------

BUSINESS_TIMEZONE = ZoneInfo("America/Argentina/Buenos_Aires")
VISIT = ("Hola", "Quiero alquilar", "Palermo", "Me interesa la primera", "<slot>")
HUMAN = ("Hola, soy <name>. Busco un 2 ambientes en Belgrano", "Quiero hablar con una persona")
BROWSING = ("Hola, quiero alquilar un 2 ambientes en Palermo", "Hasta 900 mil pesos")


@dataclass(frozen=True)
class SeedLead:
    wa_id: str
    name: str | None
    script: tuple[str, ...]
    at: datetime
    confirm: bool = False


def _last_local(now: datetime, hour: int, minute: int, days_back: int = 0) -> datetime:
    """The latest hh:mm (Buenos Aires) before `now`, `days_back` days earlier."""
    local = now.astimezone(BUSINESS_TIMEZONE)
    candidate = datetime.combine(local.date(), time(hour, minute), BUSINESS_TIMEZONE)
    if candidate >= now:
        candidate -= timedelta(days=1)
    return (candidate - timedelta(days=days_back)).astimezone(UTC)


def inbox_leads(now: datetime) -> list[SeedLead]:
    """Spread over this week and last: two out of hours (23:10), one asking for a person,
    two proposed visits, one confirmed, some still qualifying, and two from last week whose
    last message is older than 24 hours."""
    out_of_hours = _last_local(now, 23, 10)
    return [
        SeedLead("5491170000001", "Lucía Fernández", VISIT, now - timedelta(hours=3)),
        SeedLead("5491170000002", "Martín López", VISIT, out_of_hours),
        SeedLead("5491170000003", "Sofía Ruiz", HUMAN, now - timedelta(minutes=50)),
        SeedLead("5491170000004", "Diego Torres", VISIT, now - timedelta(hours=26), confirm=True),
        SeedLead("5491170000005", None, BROWSING, now - timedelta(minutes=20)),
        SeedLead("5491170000006", None, BROWSING, out_of_hours - timedelta(days=1)),
        SeedLead("5491170000007", "Carla Méndez", BROWSING, now - timedelta(days=8)),
        SeedLead("5491170000008", "Pablo Gómez", HUMAN, now - timedelta(days=9)),
    ]


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def seed_inbox(session: Session, tenant_id, owner_profile_id) -> None:
    """Runs each conversation through the WhatsApp pipeline in process. Leads whose number
    already has a thread are skipped, so running the seed again changes nothing."""
    from followup_core.conversation.application.control import Actor
    from followup_core.conversation.domain.thread import Channel, ThreadKey
    from followup_core.conversation.infrastructure.fake_llm import FakeLanguageModel
    from followup_core.conversation.infrastructure.repositories import SqlAlchemyThreadRepository
    from followup_core.messaging.application.pipeline import ApplyDeliveryStatus, IngestWebhook
    from followup_core.messaging.infrastructure.repositories import (
        SqlAlchemyConnectionRepository,
        SqlAlchemyInboundEventRepository,
        SqlAlchemyOutboundRepository,
    )
    from followup_core.notifications.infrastructure.smtp import RecordingEmailSender
    from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue
    from inmo24x7_api.container import build_lead_actions, get_messaging_services, job_handlers
    from inmo24x7_api.leads.infrastructure.repositories import SqlAlchemyLeadRepository
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    sys.path.insert(0, str(ROOT / "scripts"))
    import simulate_whatsapp

    # Seeded leads never email anyone.
    services = replace(get_messaging_services(), email=RecordingEmailSender())
    sessions = sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)
    llm = FakeLanguageModel()
    real_now = datetime.now(UTC)
    clock = _Clock(real_now)
    runner = JobRunner(
        sessions,
        lambda job_session: job_handlers(job_session, services, llm, None, clock),
        clock,
        jitter=lambda: 0.5,
    )
    debounce = timedelta(seconds=services.settings.inbound_debounce_seconds)

    def say(lead: SeedLead, number: int, text_: str, slot: str | None = None) -> None:
        payload = simulate_whatsapp.message_payload(
            text_,
            sender=lead.wa_id,
            phone_number_id=DEV_PHONE_NUMBER_ID,
            slot=slot,
            name=lead.name or "Visitante",
            wamid=f"wamid.seed.{lead.wa_id}.{number}",
            timestamp=int(clock.now.timestamp()),
        )
        with sessions() as ingest_session:
            outbound = SqlAlchemyOutboundRepository(ingest_session)
            IngestWebhook(
                SqlAlchemyConnectionRepository(ingest_session),
                SqlAlchemyInboundEventRepository(ingest_session),
                ApplyDeliveryStatus(outbound),
                SqlAlchemyJobQueue(ingest_session, clock),
                debounce,
                clock,
            ).execute(payload)
            ingest_session.commit()
        # The burst settles, the turn runs, the log sender's statuses follow.
        clock.now += debounce + timedelta(seconds=1)
        runner.run_due()
        clock.now += timedelta(seconds=5)
        runner.run_due()

    def offered_slot(wa_id: str) -> tuple[str, str]:
        with sessions() as read:
            row = read.execute(
                text(
                    "SELECT m.payload FROM conversation_messages m "
                    "JOIN conversation_threads t ON t.id = m.thread_id "
                    "WHERE t.visitor_id = :wa_id AND m.payload ? 'slots' ORDER BY m.seq DESC"
                ),
                {"wa_id": wa_id},
            ).first()
        assert row is not None, "the agent offered no visit slots"
        slot = row[0]["slots"][0]
        return slot["id"], slot.get("short_label") or slot["label"]

    threads = SqlAlchemyThreadRepository(session)
    for lead in inbox_leads(real_now):
        if threads.get_by_key(ThreadKey(tenant_id, Channel.WHATSAPP, lead.wa_id)) is not None:
            continue
        clock.now = lead.at
        script = [*lead.script, f"Me llamo {lead.name}"] if lead.script is VISIT else lead.script
        script = [line.replace("<name>", lead.name or "Sofía") for line in script]
        for number, line in enumerate(script):
            if line == "<slot>":
                slot_id, title = offered_slot(lead.wa_id)
                say(lead, number, title, slot=slot_id)
            else:
                say(lead, number, line)
            clock.now += timedelta(minutes=1)
        if lead.confirm:
            with sessions() as act:
                stored = SqlAlchemyLeadRepository(act).get_by_thread(
                    threads.get_by_key(ThreadKey(tenant_id, Channel.WHATSAPP, lead.wa_id)).id  # type: ignore[union-attr]
                )
                assert stored is not None
                (visit,) = [v for v in SqlAlchemyLeadRepository(act).visits(stored.id)]
                build_lead_actions(act, services.settings, clock).confirm.execute(
                    tenant_id, stored.id, visit.id, Actor(owner_profile_id, "Dueño")
                )
                act.commit()
            clock.now += timedelta(seconds=10)
            runner.run_due()
    # Anything left for later (the 15-minute "in progress" emails) runs now, silently.
    clock.now = real_now + timedelta(minutes=20)
    runner.run_due()


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
