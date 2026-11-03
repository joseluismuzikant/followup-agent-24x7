"""New-lead emails to the business ("Avisarme de cada lead en"), sent as jobs.

Only real leads (never simulator tests), at most one email of each kind per lead (dedupe
keys), to the tenant's notification emails:
- on the hand-off: "Nueva consulta" with the answers and the visit or the request;
- 15 minutes after the first message, if there is still no hand-off: "Consulta en curso".
"""

import html
import logging
from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from followup_core.notifications.domain.email import Email, EmailError, EmailSender
from followup_core.scheduling.domain.jobs import Job, JobError, JobQueue, NewJob
from followup_core.tenancy.domain.business_settings_repository import BusinessSettingsRepository

from ..display import KnownRow, known_rows, looking_for
from ..domain.lead import HandOffReason, Lead, VisitStatus
from ..domain.slots import slot_label
from .queries import GetLead

logger = logging.getLogger("inmo24x7.lead_email")

HANDOFF_EMAIL_JOB = "lead.email_handoff"
IN_PROGRESS_EMAIL_JOB = "lead.email_in_progress"
IN_PROGRESS_DELAY = timedelta(minutes=15)


def handoff_email_job(lead: Lead) -> NewJob:
    return NewJob(
        HANDOFF_EMAIL_JOB,
        {"tenant_id": str(lead.tenant_id), "lead_id": str(lead.id)},
        dedupe_key=f"lead-email:{lead.id}:handoff",
    )


def in_progress_email_job(lead: Lead) -> NewJob:
    return NewJob(
        IN_PROGRESS_EMAIL_JOB,
        {"tenant_id": str(lead.tenant_id), "lead_id": str(lead.id)},
        run_at=lead.created_at + IN_PROGRESS_DELAY,
        dedupe_key=f"lead-email:{lead.id}:in_progress",
    )


def queue_lead_emails(queue: JobQueue, lead: Lead, *, started: bool, handed_off_now: bool) -> None:
    """Called after every turn in the turn's transaction; dedupe keys keep it to one each."""
    if lead.is_test:
        return
    if started:
        queue.enqueue(in_progress_email_job(lead))
    if handed_off_now:
        queue.enqueue(handoff_email_job(lead))


def _who(lead: Lead) -> str:
    return lead.visitor_name or lead.contact or "Sin nombre"


class SendLeadEmail:
    def __init__(
        self,
        get_lead: GetLead,
        settings: BusinessSettingsRepository,
        sender: EmailSender,
        panel_url: str,
    ) -> None:
        self._get_lead = get_lead
        self._settings = settings
        self._sender = sender
        self._panel_url = panel_url.rstrip("/")

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        detail = self._get_lead.execute(tenant_id, UUID(job.payload["lead_id"]))
        lead = detail.lead
        if lead.is_test:
            return
        if job.kind == IN_PROGRESS_EMAIL_JOB and lead.is_handed_off:
            return  # the hand-off email covers it
        settings = self._settings.get(tenant_id)
        if settings is None or not settings.notification_emails:
            return
        zone = ZoneInfo(settings.timezone)
        rows = known_rows(
            detail.agent_config,
            {"answers": lead.answers, "visitor_name": lead.visitor_name, "contact": lead.contact},
        )
        visit = next((v for v in detail.visits if v.status is VisitStatus.PROPOSED), None)
        handoff = job.kind == HANDOFF_EMAIL_JOB
        if handoff:
            subject = f"Nueva consulta: {_who(lead)}"
            if visit is not None:
                headline = (
                    f"Pidió visitar {visit.property_label} el "
                    f"{slot_label(visit.starts_at.astimezone(zone))}. Confirmale el horario."
                )
            elif lead.hand_off_reason is HandOffReason.HUMAN:
                headline = "Pidió hablar con alguien del equipo."
            else:
                headline = "Dejó sus datos para que alguien del equipo lo contacte."
        else:
            subject = f"Consulta en curso: {_who(lead)}"
            headline = "Todavía está conversando con tu agente. Esto es lo que sabemos hasta ahora."
        summary = looking_for(lead.answers)
        if summary:
            subject += f" · {summary}"
        link = f"{self._panel_url}/consultas?lead={lead.id}"
        email = Email(
            to=list(settings.notification_emails),
            subject=subject[:200],
            text=_text(headline, rows, lead, link),
            html=_html(headline, rows, lead, link),
        )
        try:
            self._sender.send(email)
        except EmailError as error:
            raise JobError(f"email_{error.code}") from error
        logger.info(
            "lead_email_sent",
            extra={"tenant_id": str(tenant_id), "lead_id": str(lead.id), "kind": job.kind},
        )


def _channel(lead: Lead) -> str:
    return "WhatsApp" if lead.channel == "whatsapp" else "el simulador"


def _text(headline: str, rows: list[KnownRow], lead: Lead, link: str) -> str:
    lines = [headline, "", f"Llegó por {_channel(lead)}.", ""]
    lines += [f"{row.label}: {row.value or 'Pendiente'}" for row in rows]
    lines += ["", f"Ver la consulta: {link}", "", "— inmo24x7"]
    return "\n".join(lines)


def _html(headline: str, rows: list[KnownRow], lead: Lead, link: str) -> str:
    items = "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#666'>{html.escape(row.label)}</td>"
        f"<td style='padding:4px 0'>{html.escape(row.value or 'Pendiente')}</td></tr>"
        for row in rows
    )
    return (
        "<div style='font-family:sans-serif;font-size:14px;color:#111'>"
        f"<p style='font-size:16px'><strong>{html.escape(headline)}</strong></p>"
        f"<p>Llegó por {_channel(lead)}.</p>"
        f"<table>{items}</table>"
        f"<p style='margin-top:20px'><a href='{html.escape(link)}' "
        "style='background:#111;color:#fff;padding:10px 16px;border-radius:6px;"
        "text-decoration:none'>Ver la consulta</a></p>"
        "<p style='color:#888;font-size:12px'>inmo24x7</p></div>"
    )
