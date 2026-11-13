"""Cuentas Claras's job worker: `python -m cuentas_claras_api.worker`, claiming only the
cuentas_claras queue: WhatsApp (sending, read receipts, the health sweep, the reconnect
email; inbound messages are stored on the client's thread and emailed to the owner), the
reminders (the daily planner, the sends, the escalation emails, the templates and their
status sync) and the invitation emails."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from followup_core.conversation.application.threads import ReplyWithoutAgent
from followup_core.conversation.infrastructure.repositories import (
    PostgresAdvisoryThreadLock,
    SqlAlchemyMessageRepository,
    SqlAlchemyThreadRepository,
)
from followup_core.identity.application.accounts import INVITATION_EMAIL_JOB
from followup_core.messaging.application.health import health_sweep_job
from followup_core.messaging.application.pipeline import (
    PROCESS_JOB,
    PURGE_JOB,
    PurgePayloads,
    SendQueued,
    StoreInbound,
    purge_job,
)
from followup_core.messaging.application.reconnect import REMINDERS_STOPPED
from followup_core.messaging.infrastructure.repositories import (
    SqlAlchemyInboundEventRepository,
    SqlAlchemyOutboundRepository,
)
from followup_core.notifications.domain.email import EmailSender
from followup_core.scheduling.domain.jobs import JobHandlers
from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue
from followup_platform import invitations
from followup_platform.logging import configure_logging
from followup_platform.observability import init_sentry
from followup_platform.whatsapp import wiring
from followup_platform.whatsapp.wiring import MessagingServices
from followup_platform.worker import run
from sqlalchemy.orm import Session

from .config import get_settings
from .container import (
    active_tenants,
    get_messaging_services,
    load_context,
    notification_recipients,
    plan_reminders,
    utc_now,
)
from .database import SessionLocal
from .payments.infrastructure.repository import SqlAlchemyPaymentRequestRepository
from .product import PRODUCT
from .reminders.application.notify import (
    REPLY_EMAIL_JOB,
    QueueReplyEmail,
    SendEscalationEmail,
    SendReplyEmail,
)
from .reminders.application.planner import (
    ESCALATION_EMAIL_JOB,
    PLAN_JOB,
    PLAN_SWEEP_JOB,
    SEND_REMINDER_JOB,
    PlanSweep,
    sweep_job,
)
from .reminders.application.send import ReminderThreads, SendReminder
from .reminders.application.templates import (
    ENSURE_TEMPLATES_JOB,
    SUBMIT_TEMPLATE_JOB,
    SYNC_SWEEP_JOB,
    SYNC_TEMPLATES_JOB,
    EnsureTemplates,
    SubmitTemplate,
    SyncSweep,
    SyncTemplates,
    sync_sweep_job,
)
from .reminders.infrastructure.repositories import (
    SqlAlchemyOwedInvoices,
    SqlAlchemyReminderLog,
    SqlAlchemyTemplateRepository,
)
from .reminders.infrastructure.template_graph import TemplateGraphFor, template_graph_for

__all__ = ["build_runner", "job_handlers", "main", "schedule_housekeeping"]


class NoAgentConfig:
    """Cuentas Claras has no agent yet (Day 10): its threads are at version 0 and only
    store messages (ReplyWithoutAgent reads nothing else)."""

    def current(self, tenant_id: UUID) -> tuple[int, None]:
        return 0, None

    def at_version(self, tenant_id: UUID, version: int) -> None:
        return None


def job_handlers(
    session: Session,
    email: EmailSender | None = None,
    *,
    services: MessagingServices | None = None,
    clock: Callable[[], datetime] = utc_now,
    template_graph: TemplateGraphFor | None = None,
) -> JobHandlers:
    """Every job kind and its one handler. Tests pass their own email sender, messaging
    services (fake Graph transport), clock and template graph."""
    services = services or get_messaging_services()
    if email is not None:
        services = replace(services, email=email)
    settings = services.settings
    queue = SqlAlchemyJobQueue(session, clock, PRODUCT)
    connections = wiring.connections(session, PRODUCT)
    events = SqlAlchemyInboundEventRepository(session)
    outbound = SqlAlchemyOutboundRepository(session)
    threads = SqlAlchemyThreadRepository(session)
    messages = SqlAlchemyMessageRepository(session)
    lock = PostgresAdvisoryThreadLock(session)
    is_active = wiring.tenant_is_active(session)
    templates = SqlAlchemyTemplateRepository(session)
    owed = SqlAlchemyOwedInvoices(session)
    log = SqlAlchemyReminderLog(session)
    graph = template_graph or template_graph_for(services.graph, services.cipher)
    recipients = notification_recipients(session)
    send_queued = SendQueued(
        outbound,
        connections,
        wiring.sender_for(services, queue),
        clock,
        wiring.connection_health(session, PRODUCT, clock),
        is_active,
    )
    return JobHandlers(
        [
            (
                PROCESS_JOB,
                StoreInbound(
                    events,
                    connections,
                    lock,
                    ReplyWithoutAgent(threads, messages, lock, NoAgentConfig(), clock),  # type: ignore[arg-type]
                    queue,
                    QueueReplyEmail(queue),
                    timedelta(seconds=settings.inbound_debounce_seconds),
                    clock,
                ),
            ),
            *wiring.whatsapp_job_handlers(
                session,
                services,
                PRODUCT,
                product_name="Cuentas Claras",
                stopped=REMINDERS_STOPPED,
                clock=clock,
            ),
            # Payloads older than 30 days are dropped whoever runs it (idempotent, all
            # products).
            (PURGE_JOB, PurgePayloads(events, queue, clock)),
            (
                INVITATION_EMAIL_JOB,
                invitations.invitation_email_handler(
                    session, PRODUCT, services.email, "Cuentas Claras", settings.panel_url
                ),
            ),
            (PLAN_JOB, plan_reminders(session, clock)),
            (PLAN_SWEEP_JOB, PlanSweep(active_tenants(session), queue, clock)),
            (
                SEND_REMINDER_JOB,
                SendReminder(
                    load_context(session, clock),
                    owed,
                    log,
                    ReminderThreads(threads, messages, lock),
                    outbound,
                    SqlAlchemyPaymentRequestRepository(session).add,
                    send_queued,
                    is_active,
                    clock,
                ),
            ),
            (
                ESCALATION_EMAIL_JOB,
                SendEscalationEmail(
                    owed, recipients, services.email, settings.panel_url, is_active
                ),
            ),
            (
                REPLY_EMAIL_JOB,
                SendReplyEmail(owed, recipients, services.email, settings.panel_url, is_active),
            ),
            (ENSURE_TEMPLATES_JOB, EnsureTemplates(templates, connections, queue, clock)),
            (
                SUBMIT_TEMPLATE_JOB,
                SubmitTemplate(
                    templates,
                    connections,
                    graph,
                    settings.panel_url,
                    wiring.business_name(session),
                    clock,
                ),
            ),
            (SYNC_TEMPLATES_JOB, SyncTemplates(templates, connections, graph, clock)),
            (SYNC_SWEEP_JOB, SyncSweep(templates.tenants_with_templates, queue, clock)),
        ]
    )


def build_runner() -> JobRunner:
    return JobRunner(SessionLocal, lambda session: job_handlers(session), queue=PRODUCT)


def schedule_housekeeping() -> None:
    """The recurring jobs, in this product's queue (each dedupe key keeps one per period):
    the daily purge and reminder planning, the 6-hourly WhatsApp health and template sync."""
    now = datetime.now(UTC)
    with SessionLocal() as session:
        queue = SqlAlchemyJobQueue(session, queue=PRODUCT)
        queue.enqueue(purge_job(now))
        queue.enqueue(health_sweep_job(now))
        queue.enqueue(sweep_job(now))
        queue.enqueue(sync_sweep_job(now))
        session.commit()


def main() -> int:
    configure_logging()
    settings = get_settings()
    init_sentry(settings, "cuentas-claras-worker")
    return run(settings, build_runner, schedule_housekeeping)


if __name__ == "__main__":
    raise SystemExit(main())
