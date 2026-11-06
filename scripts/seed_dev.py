"""Seed the local development database (AUTH_MODE=dev).

    uv run --all-packages python scripts/seed_dev.py            # seed (idempotent)
    uv run --all-packages python scripts/seed_dev.py --reset    # drop everything, migrate, seed

Everything goes through the real use cases (sign-up, agent setup, onboarding, property
import, suspension, the WhatsApp health rules), so the seed stays valid as the domain changes.
Both products are seeded: inmo24x7 as described below, then Cuentas Claras (admin@local.test
as administrator of its backoffice too, and "Ascensores Delta" with the sample invoices).
The backoffice gets one business in each state S8 shows: trial with WhatsApp (verification
pending), onboarding 2 de 5 for three days, WhatsApp in error with Meta's code 190, suspended,
and one created by an admin whose owner has not signed up yet. The inbox and the dashboard get about
eight WhatsApp leads, created by the real pipeline (signed webhook payloads, worker handlers,
the fake model and the log sender) on a clock set to this week and last week. Refuses to run
with APP_ENV=production, and --reset only touches a database on localhost.
"""

from __future__ import annotations

import argparse
import os
import sys
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from _cli import ROOT, load_env_file

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SAMPLE_PROPERTIES = ROOT / "docs" / "samples" / "propiedades.csv"
SAMPLE_INVOICES = ROOT / "docs" / "samples" / "cuentas-claras" / "facturas.csv"
# The sample's due dates are relative to this day (docs/samples/cuentas-claras/README.md).
SAMPLE_REFERENCE = date(2026, 11, 2)
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
# Filled while seeding: each invited email's link token (None if invited by an earlier run).
INVITATION_LINKS: dict[str, str | None] = {}
CC_INVITATION_LINKS: dict[str, str | None] = {}


# Every seeded account signs in with this password; invited ones get the temporary one and
# must change it first (docs/local-test-guide.md).
DEV_PASSWORD = "local-1234"
TEMPORARY_PASSWORD = "temporal-1234"


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
NEW = DevAccount(
    "nuevo@local.test",
    "Nuevo Inmo",
    f"invitado ({TEMPORARY_PASSWORD}): cambio de clave obligatorio y el asistente desde cero",
)
PALERMO = DevAccount(
    "duena@palermoprop.test",
    "Palermo Propiedades",
    "en prueba, WhatsApp conectado y verificación de Meta pendiente",
)
BELGRANO = DevAccount(
    "dueno@belgranohogar.test", "Belgrano Hogar", "onboarding 2 de 5 desde hace 3 días"
)
CABALLITO = DevAccount(
    "duena@caballitoinmuebles.test",
    "Caballito Inmuebles",
    "WhatsApp con error de Meta 190 (permiso vencido)",
)
NORTE = DevAccount("dueno@nortebienes.test", "Norte Bienes Raíces", "cuenta suspendida")
INVITED = DevAccount(
    "invitada@villaurquiza.test",
    "Villa Urquiza Propiedades",
    f"invitada ({TEMPORARY_PASSWORD}), todavía no entró: probá el link de la invitación",
)
ACCOUNTS = (ADMIN, OWNER, NEW, PALERMO, BELGRANO, CABALLITO, NORTE, INVITED)

# Cuentas Claras. The same email is a different profile in each product; nuevo@local.test is
# invited here too (one account, one password, a business in each product).
CC_ADMIN = DevAccount(
    "admin@local.test", "Plataforma", "administrador de la plataforma (backoffice)"
)
CC_OWNER = DevAccount(
    "dueno@ascensoresdelta.test",
    "Ascensores Delta",
    "dueño de Ascensores Delta: 40 facturas de 25 clientes, onboarding terminado",
)
CC_NEW = DevAccount(
    NEW.email,
    "Nuevo Negocio",
    f"invitado ({TEMPORARY_PASSWORD}): el asistente de Cuentas Claras desde cero",
)
CC_SUSPENDED = DevAccount(
    "dueno@monitoreosur.test", "Monitoreo Sur", "cuenta suspendida (Tu cuenta está suspendida)"
)
CC_SETUP = DevAccount(
    "duena@soporteitnorte.test",
    "Soporte IT Norte",
    "asistente sin terminar (en Tus facturas), sin facturas: Inicio vacío",
)
CC_INVITED = DevAccount(
    "invitado@matafuegosnorte.test",
    "Matafuegos Norte",
    f"invitado ({TEMPORARY_PASSWORD}), todavía no entró: probá el link de la invitación",
)
CC_ACCOUNTS = (CC_ADMIN, CC_OWNER, CC_SUSPENDED, CC_SETUP, CC_NEW, CC_INVITED)


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
    command.upgrade(config, "heads")


def _directory(session: Session):
    from followup_platform.identity import build_account_directory
    from inmo24x7_api.config import get_settings

    return build_account_directory(get_settings(), session)


def _business(session: Session, container, account: DevAccount, business_type: str):
    """The business an admin created for this email ("Dar de alta"); none twice."""
    from followup_core.identity.infrastructure.dev_verifier import dev_user_id
    from followup_core.tenancy.domain.errors import OwnerEmailTakenError

    assert account.business is not None
    # Created (or claimed) by a previous run: nothing to do.
    with suppress(OwnerEmailTakenError):
        container.create_business_use_case(session).execute(
            dev_user_id(ADMIN.email), account.business, business_type, account.email
        )


def _ready(session: Session, account: DevAccount, container=None, business_type=""):
    """A business and its owner, signed up with DEV_PASSWORD (no forced change): the real
    invitation path minus the email, then the owner's first sign-in."""
    from followup_core.identity.domain.account import Account
    from followup_core.identity.infrastructure.accounts import SqlAlchemyAccountRepository

    if container is None:
        import inmo24x7_api.container as container

        business_type = business_type or "inmobiliaria"
    _business(session, container, account, business_type)
    accounts = SqlAlchemyAccountRepository(session)
    found = accounts.get_by_email(account.email)
    if found is None:
        user_id = _directory(session).create_user(account.email, DEV_PASSWORD)
        now = datetime.now(UTC)
        accounts.add(Account(user_id, account.email, False, now, now))
    else:
        user_id = found.user_id
    return container.sign_up_use_case(session).execute(user_id, account.email)


def _invite(session: Session, account: DevAccount, container, business_type: str) -> str | None:
    """Invited and not in yet: the account has TEMPORARY_PASSWORD and the invitation email is
    queued. The link's token, or None when a previous run already invited them."""
    from followup_core.identity.application.accounts import InviteOwner
    from followup_core.identity.infrastructure.accounts import (
        SqlAlchemyAccountRepository,
        SqlAlchemyInvitationRepository,
    )
    from followup_core.identity.infrastructure.dev_verifier import dev_user_id
    from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
    from followup_core.tenancy.infrastructure.audit_repository import (
        SqlAlchemyAuditLog,
        SqlAlchemyOwnerClaimRepository,
    )

    product = container.PRODUCT
    if SqlAlchemyInvitationRepository(session).latest_for(product, account.email):
        return None
    _business(session, container, account, business_type)
    claim = SqlAlchemyOwnerClaimRepository(session, product).get_open(account.email)
    assert claim is not None
    return (
        InviteOwner(
            product,
            SqlAlchemyAccountRepository(session),
            _directory(session),
            SqlAlchemyOwnerClaimRepository(session, product),
            SqlAlchemyInvitationRepository(session),
            SqlAlchemyJobQueue(session, queue=product),
            SqlAlchemyAuditLog(session),
            password_factory=lambda: TEMPORARY_PASSWORD,
        )
        .execute(dev_user_id(ADMIN.email), claim.tenant_id)
        .token
    )


def _configure_owner(session: Session, tenant_id, profile_id) -> None:
    from followup_core.tenancy.application.agent_setup import AgentConfigDraft, QuestionDraft
    from inmo24x7_api.container import (
        advance_onboarding_use_case,
        get_agent_setup_use_case,
        import_properties_use_case,
        save_agent_setup_use_case,
    )
    from inmo24x7_api.product import OnboardingStep
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


def _connect_whatsapp(
    session: Session,
    tenant_id,
    phone_number_id: str = DEV_PHONE_NUMBER_ID,
    display: str = "+54 9 11 5555-0100",
) -> None:
    """A fake number with the log sender: scripts/simulate_whatsapp.py talks to it and
    nothing ever reaches Meta."""
    from followup_core.identity.infrastructure.dev_verifier import dev_user_id
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
            phone_number_id=phone_number_id,
            waba_id=f"dev-waba-{phone_number_id.rsplit('-', 1)[-1]}",
            display_phone_number=display,
            access_token="dev-token-not-used-by-the-log-sender",
            sender=SenderKind.LOG,
        ),
        dev_user_id(ADMIN.email),
    )


def seed(session: Session) -> None:
    """Creates the dev accounts; running it again changes nothing."""
    from followup_core.identity.application.set_platform_admin import SetPlatformAdmin
    from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository

    _ready(session, ADMIN)
    SetPlatformAdmin(SqlAlchemyProfileRepository(session)).execute(ADMIN.email)
    owner = _ready(session, OWNER)
    _configure_owner(session, owner.tenant.id, owner.profile.id)
    session.commit()
    seed_inbox(session, owner.tenant.id, owner.profile.id)
    seed_backoffice(session)
    seed_cuentas_claras(session)


# --- Cuentas Claras ---------------------------------------------------------------------------


def shifted_invoices(today: date) -> bytes:
    """The sample CSV with every date moved so that its reference date is `today`: the same
    mix of overdue, due soon and paid invoices whenever the seed runs."""
    delta = today - SAMPLE_REFERENCE
    lines = SAMPLE_INVOICES.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(";")
    dates = [header.index(name) for name in ("fecha_emision", "vencimiento", "fecha_pago")]
    out = [lines[0]]
    for line in lines[1:]:
        cells = line.split(";")
        for index in dates:
            if cells[index]:
                moved = datetime.strptime(cells[index], "%d/%m/%Y").date() + delta
                cells[index] = moved.strftime("%d/%m/%Y")
        out.append(";".join(cells))
    return ("\n".join(out) + "\n").encode("utf-8")


def seed_cuentas_claras(session: Session) -> None:
    """Runs Cuentas Claras's real sign-up, import and onboarding; again, it changes nothing."""
    import cuentas_claras_api.container as container
    from cuentas_claras_api.container import (
        advance_onboarding_use_case,
        import_invoices_use_case,
        timezone_of,
        utc_now,
    )
    from cuentas_claras_api.invoices.domain.status import today_in
    from cuentas_claras_api.invoices.infrastructure.repository import SqlAlchemyInvoiceRepository
    from cuentas_claras_api.product import PRODUCT
    from followup_core.identity.application.set_platform_admin import SetPlatformAdmin
    from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository

    admin = _ready(session, CC_ADMIN, container, "otro")
    SetPlatformAdmin(SqlAlchemyProfileRepository(session, PRODUCT)).execute(CC_ADMIN.email)
    owner = _ready(session, CC_OWNER, container, "mantenimiento")
    tenant_id = owner.tenant.id
    if not SqlAlchemyInvoiceRepository(session).has_any(tenant_id):
        today = today_in(timezone_of(session)(tenant_id), utc_now())
        report = import_invoices_use_case(session, utc_now).execute(
            tenant_id, owner.profile.id, "facturas.csv", shifted_invoices(today)
        )
        if report.failed_rows:
            raise SeedError(
                f"The sample invoices did not import: {len(report.failed_rows)} rows failed."
            )
    advance = advance_onboarding_use_case(session)
    for step in ("reminders", "connect", "done"):
        advance.execute(tenant_id, step)
    CC_INVITATION_LINKS[CC_NEW.email] = _invite(session, CC_NEW, container, "otro")

    # Suspended, with a reason only admins see.
    suspended = _ready(session, CC_SUSPENDED, container, "seguridad")
    if not suspended.tenant.is_suspended:
        container.tenant_suspension_use_case(session).suspend(
            admin.profile.id, suspended.tenant.id, "Pidió pausar el servicio hasta marzo."
        )
    # Came in once and stopped at "Tus facturas": no invoices, Inicio's empty state.
    _ready(session, CC_SETUP, container, "soporte_it")
    # Invited by an admin; has not come in yet.
    CC_INVITATION_LINKS[CC_INVITED.email] = _invite(session, CC_INVITED, container, "mantenimiento")
    session.commit()


# --- Backoffice (S8, S9) ----------------------------------------------------------------------


def _save_default_agent(session: Session, tenant_id, profile_id) -> None:
    from followup_core.tenancy.application.agent_setup import AgentConfigDraft, QuestionDraft
    from inmo24x7_api.container import get_agent_setup_use_case, save_agent_setup_use_case

    setup = get_agent_setup_use_case(session).execute(tenant_id)
    defaults = setup.defaults
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


def seed_backoffice(session: Session) -> None:
    """One business per S8 state, with its audit events. Running it again changes nothing."""
    from followup_core.identity.infrastructure.dev_verifier import dev_user_id
    from followup_core.messaging.domain.connection import BusinessVerification
    from followup_core.messaging.infrastructure.repositories import (
        SqlAlchemyConnectionRepository,
    )
    from inmo24x7_api.container import connection_health, tenant_suspension_use_case
    from sqlalchemy import text

    admin = dev_user_id(ADMIN.email)
    connections = SqlAlchemyConnectionRepository(session)

    # Trial, everything done, WhatsApp connected while Meta reviews the business.
    palermo = _ready(session, PALERMO)
    _configure_owner_without_inbox(session, palermo.tenant.id, palermo.profile.id, "dev-phone-2")
    connection = connections.get_by_tenant(palermo.tenant.id)
    if connection is not None and connection.business_verification is not (
        BusinessVerification.PENDING
    ):
        connections.save(replace(connection, business_verification=BusinessVerification.PENDING))

    # Onboarding 2 de 5 (account + agent), stuck for three days: "Necesitan ayuda".
    belgrano = _ready(session, BELGRANO)
    _save_default_agent(session, belgrano.tenant.id, belgrano.profile.id)
    session.execute(
        text("UPDATE tenants SET created_at = :at WHERE id = :id AND created_at > :at"),
        {"at": datetime.now(UTC) - timedelta(days=3), "id": belgrano.tenant.id},
    )

    # WhatsApp in error: the customer removed the app's access (190) 26 hours ago.
    caballito = _ready(session, CABALLITO)
    _configure_owner_without_inbox(
        session, caballito.tenant.id, caballito.profile.id, "dev-phone-3"
    )
    connection = connections.get_by_tenant(caballito.tenant.id)
    if connection is not None and not connection.is_failing:
        failed_at = datetime.now(UTC) - timedelta(hours=26)
        connection_health(session, lambda: failed_at).failed(connection, "190")

    # Suspended, with a reason only admins see.
    norte = _ready(session, NORTE)
    _save_default_agent(session, norte.tenant.id, norte.profile.id)
    if not norte.tenant.is_suspended:
        tenant_suspension_use_case(session).suspend(
            admin, norte.tenant.id, "Pidió pausar el servicio hasta marzo."
        )

    # Created by an admin and invited; she has not come in yet.
    import inmo24x7_api.container as container

    INVITATION_LINKS[INVITED.email] = _invite(session, INVITED, container, "inmobiliaria")
    INVITATION_LINKS[NEW.email] = _invite(session, NEW, container, "inmobiliaria")
    session.commit()


def _configure_owner_without_inbox(session: Session, tenant_id, profile_id, phone: str) -> None:
    """Agent saved, wizard finished, the sample properties and a log-sender number."""
    from inmo24x7_api.container import advance_onboarding_use_case, import_properties_use_case
    from inmo24x7_api.product import OnboardingStep
    from inmo24x7_api.properties.infrastructure.repositories import SqlAlchemyPropertyRepository

    _save_default_agent(session, tenant_id, profile_id)
    advance = advance_onboarding_use_case(session)
    for step in (OnboardingStep.TRY, OnboardingStep.WHATSAPP, OnboardingStep.DONE):
        advance.execute(tenant_id, step)
    if not SqlAlchemyPropertyRepository(session).has_any(tenant_id):
        import_properties_use_case(session).execute(
            tenant_id, profile_id, SAMPLE_PROPERTIES.name, SAMPLE_PROPERTIES.read_bytes()
        )
    suffix = phone.rsplit("-", 1)[-1]
    _connect_whatsapp(session, tenant_id, phone, f"+54 9 11 5555-010{suffix}")


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

    print("\nListo. Entrá con estos emails (AUTH_MODE=dev).")
    print(f"Clave de todas las cuentas listas: {DEV_PASSWORD}")
    print("\ninmo24x7 (panel http://localhost:5173, backoffice http://localhost:5174):")
    for account in ACCOUNTS:
        print(f"  {account.email:<30} {account.what}")
    _print_links("http://localhost:5173", INVITATION_LINKS)
    print("\nCuentas Claras (panel http://localhost:5175, backoffice http://localhost:5176):")
    for account in CC_ACCOUNTS:
        print(f"  {account.email:<30} {account.what}")
    _print_links("http://localhost:5175", CC_INVITATION_LINKS)
    return 0


def _print_links(panel: str, links: dict[str, str | None]) -> None:
    for email, token in links.items():
        if token:
            print(f"  link de invitación de {email}: {panel}/invitacion?token={token}")
        else:
            print(f"  {email}: ya invitado antes (el link está en Mailpit, http://localhost:8025)")


if __name__ == "__main__":
    raise SystemExit(main())
