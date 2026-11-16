"""The send job: one WhatsApp reminder for one client on one day. Everything is checked
again when it runs (still owed, not promised, the window, the holiday, the template, the
connection); "not yet" is a Reschedule, never a failure.

The message is stored in the client's WhatsApp thread (where its replies land) and goes
out through core's SendQueued, so Meta's errors get the same handling and backoff as every
other message: a retryable error retries this job, a permanent one fails this reminder,
and a revoked token pauses the business's reminders (nothing goes out late: the part is
closed, and the planner tries again once WhatsApp is reconnected)."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID, uuid4

from followup_core.conversation.domain.repositories import (
    MessageRepository,
    ThreadLock,
    ThreadRepository,
)
from followup_core.conversation.domain.thread import (
    Author,
    Channel,
    Direction,
    Message,
    Thread,
    ThreadKey,
    ThreadStatus,
)
from followup_core.infrastructure import log_context
from followup_core.messaging.application.health import SEND_JOB
from followup_core.messaging.domain.outbound import DeliveryStatus, OutboundPart
from followup_core.messaging.domain.repositories import OutboundRepository
from followup_core.scheduling.domain.jobs import Job, JobStatus, Reschedule, RetryLater

from ...clients.domain.client import Client
from ...invoices.domain.invoice import Invoice
from ...payments.domain.requests import PaymentRequest
from ..domain.events import Outcome, ReminderEvent, ReminderSend, SendStatus, SkipReason
from ..domain.next_action import Connection
from ..domain.planning import InvoiceState, plan, template_kind
from ..domain.policy import ReminderStep, TemplateKind
from ..domain.repositories import OwedInvoices, ReminderLog
from ..domain.templates import InvoiceLine, render, values
from .context import Clock, LoadContext, ReminderContext, utc_now

logger = logging.getLogger("cuentas_claras.reminders")

# SendQueued's own codes for "not now" (not Meta's): the reminder is paused, not failed.
_PAUSING = {"not_connected", "tenant_suspended"}

SendQueuedJob = Callable[[Job], RetryLater | None]
AddPaymentRequest = Callable[[PaymentRequest], None]


@dataclass(frozen=True, slots=True)
class Due:
    invoice: Invoice
    step: ReminderStep


def visitor_id(e164: str) -> str:
    """The thread's id for a client's number: the wa_id form (digits, the 9 kept)."""
    return e164.lstrip("+")


class ReminderThreads:
    """The client's WhatsApp thread: created on the first reminder, reused by replies."""

    def __init__(
        self, threads: ThreadRepository, messages: MessageRepository, lock: ThreadLock
    ) -> None:
        self._threads = threads
        self._messages = messages
        self._lock = lock

    def add_reminder(
        self, tenant_id: UUID, wa_id: str, text: str, payload: dict, now: datetime
    ) -> Message:
        key = ThreadKey(tenant_id, Channel.WHATSAPP, wa_id)
        self._lock.acquire(key)
        thread = self._threads.get_by_key(key)
        if thread is None:
            thread = Thread(uuid4(), key, 0, ThreadStatus.OPEN, now, None)
            self._threads.add(thread)
        message = Message(
            uuid4(), thread.id, Direction.OUTBOUND, Author.AGENT, text, now, payload=payload
        )
        self._messages.append(message)
        self._threads.touch(thread.id, now)
        return message


class SendReminder:
    def __init__(
        self,
        load: LoadContext,
        owed: OwedInvoices,
        log: ReminderLog,
        threads: ReminderThreads,
        outbound: OutboundRepository,
        add_payment_request: AddPaymentRequest,
        send_queued: SendQueuedJob,
        is_active: Callable[[UUID], bool],
        clock: Clock = utc_now,
    ) -> None:
        self._load = load
        self._owed = owed
        self._log = log
        self._threads = threads
        self._outbound = outbound
        self._add_payment_request = add_payment_request
        self._send_queued = send_queued
        self._is_active = is_active
        self._clock = clock

    def __call__(self, job: Job) -> Reschedule | RetryLater | None:
        tenant_id = UUID(job.payload["tenant_id"])
        client_id = UUID(job.payload["client_id"])
        day = date.fromisoformat(job.payload["day"])
        planned = [UUID(item) for item in job.payload.get("invoice_ids", [])]
        log_context.bind(tenant_id=tenant_id, channel=Channel.WHATSAPP.value)
        now = self._clock()

        existing = self._log.send_for(client_id, day)
        if existing is not None and existing.status is not SendStatus.PENDING:
            return None  # this client's reminder of the day already went (or failed)
        context = self._load(tenant_id)
        if existing is not None:
            return self._deliver(context, existing, now)

        today = context.calendar.today(now)
        if today < day:
            start = context.calendar.window_start(day)
            return Reschedule(start) if start else None
        skip = self._skipper(context, client_id, planned, today, now)
        if not self._is_active(tenant_id):
            return skip(SkipReason.TENANT_SUSPENDED)
        if today > day:
            return skip(SkipReason.WINDOW_CLOSED)
        if not context.calendar.is_open(now):
            when = context.calendar.send_time(today, now)
            return Reschedule(when) if when else skip(SkipReason.WINDOW_CLOSED)

        owed = self._owed.owed(tenant_id, client_id)
        due = self._due(context, owed, today)
        if not due:
            return skip(SkipReason.INVOICE_CLOSED)
        client = owed[0][1]
        skip = self._skipper(context, client_id, [item.invoice.id for item in due], today, now)
        if client.no_reminders:
            return skip(SkipReason.OPTED_OUT)
        if not client.whatsapp:
            return skip(SkipReason.NO_WHATSAPP)
        if context.connection is Connection.NONE:
            return skip(SkipReason.NOT_CONNECTED)
        if context.connection is Connection.ERROR:
            return skip(SkipReason.CONNECTION_ERROR)
        kind = (
            TemplateKind.SEVERAL
            if len(due) > 1
            else template_kind(due[0].step, due[0].invoice.due_date, today)
        )
        template = context.template(kind)
        if template is None:
            return skip(SkipReason.TEMPLATE_NOT_APPROVED, kind.value)

        invoices = [item.invoice for item in due]
        request, token = PaymentRequest.create(
            tenant_id, client.id, [invoice.id for invoice in invoices], now
        )
        self._add_payment_request(request)
        field_values = values(client.name, context.business_name, _lines(invoices))
        wa_id = visitor_id(client.whatsapp)
        message = self._threads.add_reminder(
            tenant_id,
            wa_id,
            render(template.body, field_values),
            {"kind": "reminder", "template": template.name, "payment_request": str(request.id)},
            now,
        )
        self._outbound.add(
            [
                OutboundPart(
                    uuid4(),
                    message.id,
                    0,
                    wa_id,
                    template.message_body(field_values, token),
                    DeliveryStatus.QUEUED,
                )
            ]
        )
        send = ReminderSend(
            id=uuid4(),
            tenant_id=tenant_id,
            client_id=client.id,
            day=today,
            status=SendStatus.PENDING,
            template_name=template.name,
            created_at=now,
            invoice_ids=tuple(invoice.id for invoice in invoices),
            steps=tuple((item.invoice.id, item.step.id, item.step.offset_days) for item in due),
            message_id=message.id,
            payment_request_id=request.id,
        )
        self._log.add_send(send)
        return self._deliver(context, send, now)

    def _due(
        self, context: ReminderContext, owed: Sequence[tuple[Invoice, Client]], today: date
    ) -> list[Due]:
        done = self._log.done_steps(context.tenant_id, [invoice.id for invoice, _ in owed])
        due: list[Due] = []
        for invoice, client in owed:
            state = InvoiceState(invoice.id, client.id, invoice.due_date, invoice.promised_until)
            step_plan = plan(
                state,
                context.policy,
                done[invoice.id],
                today,
                context.calendar,
                reachable=bool(client.whatsapp) and not client.no_reminders,
            )
            if step_plan.due_on(today) and step_plan.step and not step_plan.step.escalates:
                due.append(Due(invoice, step_plan.step))
        return due

    def _deliver(
        self, context: ReminderContext, send: ReminderSend, now: datetime
    ) -> RetryLater | None:
        assert send.message_id is not None
        result = self._send_queued(
            Job(
                uuid4(),
                SEND_JOB,
                {"message_ids": [str(send.message_id)]},
                now,
                JobStatus.RUNNING,
                1,
                1,
            )
        )
        if isinstance(result, RetryLater):
            return result  # Meta asked to wait: this job retries with backoff
        parts = self._outbound.for_messages([send.message_id])
        part = parts[0] if parts else None
        if part is None or part.wamid:
            self._finish(send, SendStatus.SENT, Outcome.SENT, None, now)
            logger.info("reminder_sent", extra={"invoices": len(send.invoice_ids)})
            return None
        code = part.error_code or "unknown"
        if part.status is DeliveryStatus.WAITING or code in _PAUSING:
            if part.status is DeliveryStatus.WAITING:
                # Never sent late by the reconnection: the planner sends it on a later day.
                self._outbound.mark_failed(part.id, code, now)
            self._finish(send, SendStatus.PAUSED, Outcome.SKIPPED, SkipReason.CONNECTION_ERROR, now)
            return None
        self._finish(send, SendStatus.FAILED, Outcome.FAILED, code, now)
        logger.warning("reminder_failed", extra={"meta_code": code})
        return None

    def _finish(
        self,
        send: ReminderSend,
        status: SendStatus,
        outcome: Outcome,
        reason: str | None,
        now: datetime,
    ) -> None:
        self._log.finish_send(
            send.id, status, now, reason if status is not SendStatus.SENT else None
        )
        for invoice_id, step_id, offset in send.steps:
            self._log.add_event(
                ReminderEvent(
                    tenant_id=send.tenant_id,
                    client_id=send.client_id,
                    outcome=outcome,
                    day=send.day,
                    created_at=now,
                    invoice_id=invoice_id,
                    step_id=step_id,
                    offset_days=offset,
                    reason=reason,
                    send_id=send.id,
                )
            )

    def _skipper(
        self,
        context: ReminderContext,
        client_id: UUID,
        invoice_ids: Sequence[UUID],
        today: date,
        now: datetime,
    ) -> Callable[..., None]:
        def skip(reason: SkipReason, detail: str | None = None) -> None:
            code = f"{reason.value}:{detail}" if detail else reason.value
            for invoice_id in invoice_ids or [None]:
                self._log.add_event(
                    ReminderEvent(
                        tenant_id=context.tenant_id,
                        client_id=client_id,
                        outcome=Outcome.SKIPPED,
                        day=today,
                        created_at=now,
                        invoice_id=invoice_id,
                        reason=code,
                    )
                )
            logger.info("reminder_skipped", extra={"reason": code})

        return skip


def _lines(invoices: Sequence[Invoice]) -> list[InvoiceLine]:
    return [
        InvoiceLine(
            invoice.display_number, invoice.amount, invoice.currency.value, invoice.due_date
        )
        for invoice in invoices
    ]
