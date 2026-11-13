"""Emails to the business (its notification emails from Configuración, or its owners): the
escalation ("these invoices need you now") and a client's reply to a reminder. Sent by
jobs; nothing here answers the client (the collections agent arrives on Day 10)."""

import html
import logging
from collections.abc import Callable, Sequence
from uuid import UUID

from followup_core.conversation.domain.thread import Message
from followup_core.notifications.domain.email import Email, EmailError, EmailSender
from followup_core.scheduling.domain.jobs import Job, JobError, JobQueue, NewJob

from ..domain.repositories import OwedInvoices
from ..domain.templates import format_amount, format_due

logger = logging.getLogger("cuentas_claras.notify")

REPLY_EMAIL_JOB = "reminders.reply_email"
PRODUCT_NAME = "Cuentas Claras"
MAX_SNIPPET = 80

Recipients = Callable[[UUID], Sequence[str]]


def _send(sender: EmailSender, email: Email) -> None:
    try:
        sender.send(email)
    except EmailError as error:
        raise JobError(f"email_{error.code}") from error


class SendEscalationEmail:
    def __init__(
        self,
        owed: OwedInvoices,
        recipients: Recipients,
        sender: EmailSender,
        panel_url: str,
        is_active: Callable[[UUID], bool],
    ) -> None:
        self._owed = owed
        self._recipients = recipients
        self._sender = sender
        self._panel_url = panel_url.rstrip("/")
        self._is_active = is_active

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        to = list(self._recipients(tenant_id))
        if not to or not self._is_active(tenant_id):
            return
        invoices = self._owed.invoices(
            tenant_id, [UUID(item) for item in job.payload["invoice_ids"]]
        )
        owed = [invoice for invoice in invoices if invoice.is_open]
        if not owed:
            return
        clients = self._owed.clients(tenant_id, list({invoice.client_id for invoice in owed}))
        lines = [
            (
                clients[invoice.client_id].name if invoice.client_id in clients else "—",
                invoice.display_number,
                format_amount(invoice.amount, invoice.currency.value),
                format_due(invoice.due_date),
            )
            for invoice in owed
        ]
        link = f"{self._panel_url}/facturas?tab=overdue"
        count = "1 factura" if len(lines) == 1 else f"{len(lines)} facturas"
        text = (
            f"Hola:\n\n{count} ya recibieron todos los recordatorios y siguen sin pagarse. "
            "Dejamos de escribirles: conviene que las sigas vos.\n\n"
            + "\n".join(f"· {c} — {n} — {a} — venció el {d}" for c, n, a, d in lines)
            + f"\n\nVer las facturas vencidas: {link}\n\n— {PRODUCT_NAME}"
        )
        items = "".join(
            f"<li>{html.escape(c)} — {html.escape(n)} — {html.escape(a)} — venció el {d}</li>"
            for c, n, a, d in lines
        )
        body = (
            f"<p>Hola:</p><p>{count} ya recibieron todos los recordatorios y siguen sin "
            "pagarse. Dejamos de escribirles: conviene que las sigas vos.</p>"
            f"<ul>{items}</ul>"
            f'<p><a href="{html.escape(link)}">Ver las facturas vencidas</a></p>'
            f"<p>— {PRODUCT_NAME}</p>"
        )
        _send(
            self._sender,
            Email(to=to, subject=f"Escalar al dueño: {count} sin pagar", text=text, html=body),
        )
        logger.info("escalation_email_sent", extra={"invoices": len(lines)})


def reply_email_job(tenant_id: UUID, wa_id: str, messages: Sequence[Message]) -> NewJob:
    return NewJob(
        REPLY_EMAIL_JOB,
        {
            "tenant_id": str(tenant_id),
            "wa_id": wa_id,
            "texts": [message.text for message in messages if message.text][:10],
            "content_types": [message.content_type for message in messages][:10],
        },
        dedupe_key=f"reminder-reply:{messages[-1].id}" if messages else None,
        max_attempts=5,
    )


class QueueReplyEmail:
    """StoreInbound's observer: a reply to a reminder (or any message) emails the owner."""

    def __init__(self, queue: JobQueue) -> None:
        self._queue = queue

    def __call__(self, tenant_id: UUID, wa_id: str, messages: Sequence[Message]) -> None:
        if messages:
            self._queue.enqueue(reply_email_job(tenant_id, wa_id, messages))


def snippet(texts: Sequence[str]) -> str:
    joined = " ".join(" ".join(text.split()) for text in texts)
    return joined if len(joined) <= MAX_SNIPPET else joined[: MAX_SNIPPET - 1].rstrip() + "…"


class SendReplyEmail:
    def __init__(
        self,
        owed: OwedInvoices,
        recipients: Recipients,
        sender: EmailSender,
        panel_url: str,
        is_active: Callable[[UUID], bool],
    ) -> None:
        self._owed = owed
        self._recipients = recipients
        self._sender = sender
        self._panel_url = panel_url.rstrip("/")
        self._is_active = is_active

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        to = list(self._recipients(tenant_id))
        if not to or not self._is_active(tenant_id):
            return
        wa_id = str(job.payload["wa_id"])
        client = self._owed.client_by_whatsapp(tenant_id, "+" + wa_id)
        texts = [str(item) for item in job.payload.get("texts", []) if str(item).strip()]
        media = [kind for kind in job.payload.get("content_types", []) if kind != "text"]
        if media and not texts:
            texts = ["(mandó un archivo: " + ", ".join(sorted(set(media))) + ")"]
        who = client.name if client else f"+{wa_id}"
        link = (
            f"{self._panel_url}/clientes/{client.id}" if client else f"{self._panel_url}/clientes"
        )
        quoted = snippet(texts)
        text = (
            f"{who} respondió por WhatsApp:\n\n"
            + "\n".join(f"> {item}" for item in texts)
            + "\n\nTodavía no le contestamos automáticamente: mirá la conversación y "
            f"contactalo vos.\n\nVer el cliente: {link}\n\n— {PRODUCT_NAME}"
        )
        quotes = "".join(f"<blockquote>{html.escape(item)}</blockquote>" for item in texts)
        body = (
            f"<p>{html.escape(who)} respondió por WhatsApp:</p>{quotes}"
            "<p>Todavía no le contestamos automáticamente: mirá la conversación y "
            "contactalo vos.</p>"
            f'<p><a href="{html.escape(link)}">Ver el cliente</a></p><p>— {PRODUCT_NAME}</p>'
        )
        _send(
            self._sender,
            Email(to=to, subject=f"Respondió: “{quoted}” ({who})", text=text, html=body),
        )
        logger.info("reply_email_sent", extra={"known_client": client is not None})
