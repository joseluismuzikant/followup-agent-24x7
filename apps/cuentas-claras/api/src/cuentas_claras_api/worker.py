"""Cuentas Claras's job worker: `python -m cuentas_claras_api.worker`, claiming only the
cuentas_claras queue. Today it runs the recurring core jobs and the invitation emails;
reminders arrive on Day 9."""

from datetime import UTC, datetime
from functools import lru_cache

from followup_core.identity.application.accounts import INVITATION_EMAIL_JOB
from followup_core.messaging.application.pipeline import PURGE_JOB, PurgePayloads, purge_job
from followup_core.messaging.infrastructure.repositories import SqlAlchemyInboundEventRepository
from followup_core.notifications.domain.email import EmailSender
from followup_core.notifications.infrastructure.smtp import SmtpEmailSender, SmtpSettings
from followup_core.scheduling.domain.jobs import JobHandlers
from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue
from followup_platform import invitations
from followup_platform.logging import configure_logging
from followup_platform.observability import init_sentry
from followup_platform.worker import run
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .product import PRODUCT


@lru_cache
def get_email_sender() -> EmailSender:
    settings = get_settings()
    return SmtpEmailSender(
        SmtpSettings(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
            sender=settings.email_from,
        )
    )


def job_handlers(session: Session, email: EmailSender | None = None) -> JobHandlers:
    queue = SqlAlchemyJobQueue(session, queue=PRODUCT)
    settings = get_settings()
    return JobHandlers(
        [
            # Payloads older than 30 days are dropped whoever runs it (idempotent, all
            # products).
            (PURGE_JOB, PurgePayloads(SqlAlchemyInboundEventRepository(session), queue)),
            (
                INVITATION_EMAIL_JOB,
                invitations.invitation_email_handler(
                    session,
                    PRODUCT,
                    email or get_email_sender(),
                    "Cuentas Claras",
                    settings.panel_url,
                ),
            ),
        ]
    )


def build_runner() -> JobRunner:
    return JobRunner(SessionLocal, lambda session: job_handlers(session), queue=PRODUCT)


def schedule_housekeeping() -> None:
    """The daily purge, in this product's queue (the dedupe key keeps it to one a day)."""
    with SessionLocal() as session:
        SqlAlchemyJobQueue(session, queue=PRODUCT).enqueue(purge_job(datetime.now(UTC)))
        session.commit()


def main() -> int:
    configure_logging()
    settings = get_settings()
    init_sentry(settings, "cuentas-claras-worker")
    return run(settings, build_runner, schedule_housekeeping)


if __name__ == "__main__":
    raise SystemExit(main())
