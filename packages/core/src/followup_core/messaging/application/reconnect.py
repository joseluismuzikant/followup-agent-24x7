"""S9 "Enviarle link para reconectar": an email to the business owners with a link to
Configuración → WhatsApp, where Embedded Signup runs again. Sent by a job (SMTP never runs
inside a request); the audit event is written when the admin asks for it."""

import html
import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from followup_core.notifications.domain.email import Email, EmailError, EmailSender
from followup_core.scheduling.domain.jobs import Job, JobError, JobQueue, NewJob
from followup_core.tenancy.domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog

logger = logging.getLogger("followup.reconnect")

# What stopped working, in each product's words (the email's first line).
AGENT_STOPPED = "Tu agente dejó de poder responder en WhatsApp"
REMINDERS_STOPPED = "Los recordatorios por WhatsApp dejaron de salir"

RECONNECT_EMAIL_JOB = "tenant.reconnect_email"

OwnerEmails = Callable[[UUID], Sequence[str]]
BusinessName = Callable[[UUID], str]


class RequestReconnectLink:
    def __init__(
        self,
        owners: OwnerEmails,
        queue: JobQueue,
        audit: AuditLog,
        clock: Callable[[], datetime],
    ) -> None:
        self._owners = owners
        self._queue = queue
        self._audit = audit
        self._clock = clock

    def __call__(self, tenant_id: UUID, admin_id: UUID) -> int:
        """How many owners get it (0: nobody to send it to, nothing is queued)."""
        recipients = len(self._owners(tenant_id))
        if recipients == 0:
            return 0
        now = self._clock()
        self._queue.enqueue(
            NewJob(
                RECONNECT_EMAIL_JOB,
                {"tenant_id": str(tenant_id)},
                # One per business and minute: a double click sends one email.
                dedupe_key=f"reconnect:{tenant_id}:{now:%Y%m%d%H%M}",
                max_attempts=5,
            )
        )
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.ADMIN,
                AuditAction.RECONNECT_LINK_SENT,
                {"recipients": recipients},
                actor_profile_id=admin_id,
            )
        )
        return recipients


class SendReconnectEmail:
    def __init__(
        self,
        owners: OwnerEmails,
        business_name: BusinessName,
        sender: EmailSender,
        panel_url: str,
        is_active: Callable[[UUID], bool],
        *,
        product_name: str = "inmo24x7",
        stopped: str = AGENT_STOPPED,
    ) -> None:
        self._owners = owners
        self._business_name = business_name
        self._sender = sender
        self._panel_url = panel_url.rstrip("/")
        self._is_active = is_active
        self._product_name = product_name
        self._stopped = stopped

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        recipients = list(self._owners(tenant_id))
        if not recipients or not self._is_active(tenant_id):
            return
        link = f"{self._panel_url}/configuracion#whatsapp"
        name = self._business_name(tenant_id)
        text = (
            f"Hola, {name}:\n\n"
            f"{self._stopped} porque la conexión con Meta se "
            "cortó. Volvé a conectarla en un minuto desde este link:\n\n"
            f"{link}\n\n— {self._product_name}"
        )
        body = (
            f"<p>Hola, {html.escape(name)}:</p>"
            f"<p>{html.escape(self._stopped)} porque la conexión con Meta se "
            "cortó. Volvé a conectarla en un minuto:</p>"
            f'<p><a href="{html.escape(link)}">Volver a conectar WhatsApp</a></p>'
            f"<p>— {html.escape(self._product_name)}</p>"
        )
        try:
            self._sender.send(
                Email(
                    to=recipients,
                    subject="Volvé a conectar tu WhatsApp",
                    text=text,
                    html=body,
                )
            )
        except EmailError as error:
            raise JobError(f"email_{error.code}") from error
        logger.info(
            "reconnect_email_sent",
            extra={"tenant_id": str(tenant_id), "recipients": len(recipients)},
        )
