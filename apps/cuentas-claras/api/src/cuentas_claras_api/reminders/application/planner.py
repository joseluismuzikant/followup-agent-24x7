"""The planner: once a day per business (and right after an import, a policy change or a
promise), every owed invoice gets its next step. Reminders due today become one send job
per client and day, `reminder:<client_id>:<date>` (several invoices of a client due the
same day go in one message); escalations are recorded and emailed to the owner. The send
job checks everything again when it runs."""

import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from uuid import UUID

from followup_core.scheduling.domain.jobs import Job, JobQueue, NewJob
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ..domain.events import Outcome, ReminderEvent
from ..domain.next_action import Connection
from ..domain.planning import InvoiceState, plan
from ..domain.repositories import OwedInvoices, ReminderLog
from .context import Clock, LoadContext, utc_now

logger = logging.getLogger("cuentas_claras.reminders")

PLAN_JOB = "reminders.plan"
PLAN_SWEEP_JOB = "reminders.plan_sweep"
SEND_REMINDER_JOB = "reminders.send"
ESCALATION_EMAIL_JOB = "reminders.escalation_email"
# 09:00 UTC is 06:00 in Buenos Aires: before any send window opens.
SWEEP_AT = time(9)

ActiveTenants = Callable[[], list[UUID]]
TenantIsActive = Callable[[UUID], bool]


def plan_now(queue: JobQueue, tenant_id: UUID, now: datetime) -> bool:
    """Plans a business again soon (after an import, a policy change, a promise); one per
    business and minute, however many changes."""
    return queue.enqueue(
        NewJob(
            PLAN_JOB,
            {"tenant_id": str(tenant_id)},
            dedupe_key=f"reminder-plan:{tenant_id}:{now:%Y%m%d%H%M}",
            max_attempts=5,
        )
    )


def sweep_job(now: datetime) -> NewJob:
    """The sweep of the day that contains `now` (at SWEEP_AT, or now if that passed)."""
    at = datetime.combine(now.date(), SWEEP_AT, now.tzinfo)
    return NewJob(
        PLAN_SWEEP_JOB,
        {},
        run_at=max(at, now),
        dedupe_key=f"reminder-sweep:{now:%Y-%m-%d}",
        max_attempts=3,
    )


def escalation_email_job(tenant_id: UUID, invoice_ids: list[UUID]) -> NewJob:
    ids = sorted(str(item) for item in invoice_ids)
    digest = hashlib.sha256(",".join(ids).encode()).hexdigest()[:16]
    return NewJob(
        ESCALATION_EMAIL_JOB,
        {"tenant_id": str(tenant_id), "invoice_ids": ids},
        dedupe_key=f"reminder-escalation:{tenant_id}:{digest}",
        max_attempts=5,
    )


@dataclass(frozen=True, slots=True)
class PlanResult:
    sends: int = 0
    escalated: int = 0
    promises_ended: int = 0
    paused: str | None = None  # why nothing was queued (no WhatsApp, connection error)


class PlanReminders:
    def __init__(
        self,
        load: LoadContext,
        owed: OwedInvoices,
        log: ReminderLog,
        queue: JobQueue,
        audit: AuditLog,
        is_active: TenantIsActive,
        clock: Clock = utc_now,
    ) -> None:
        self._load = load
        self._owed = owed
        self._log = log
        self._queue = queue
        self._audit = audit
        self._is_active = is_active
        self._clock = clock

    def __call__(self, job: Job) -> None:
        self.execute(UUID(job.payload["tenant_id"]))

    def execute(self, tenant_id: UUID) -> PlanResult:
        if not self._is_active(tenant_id):
            return PlanResult(paused="tenant_suspended")
        now = self._clock()
        context = self._load(tenant_id)
        today = context.calendar.today(now)
        owed = self._owed.owed(tenant_id)

        ended = 0
        current = []
        for invoice, client in owed:
            if invoice.promise_expired(today):
                # The day after the promise, the sequence resumes with the next pending step.
                invoice = invoice.remove_promise(now)
                self._owed.save_invoice(invoice)
                self._audit.record(
                    AuditEvent(
                        tenant_id,
                        now,
                        ActorKind.SYSTEM,
                        CuentasAction.PROMISE_ENDED,
                        {"invoice_id": str(invoice.id)},
                    )
                )
                ended += 1
            current.append((invoice, client))

        done = self._log.done_steps(tenant_id, [invoice.id for invoice, _ in current])
        reminders: dict[UUID, list[UUID]] = defaultdict(list)
        escalated: list[UUID] = []
        for invoice, client in current:
            state = InvoiceState(invoice.id, client.id, invoice.due_date, invoice.promised_until)
            step_plan = plan(
                state,
                context.policy,
                done[invoice.id],
                today,
                context.calendar,
                reachable=bool(client.whatsapp) and not client.no_reminders,
            )
            if not step_plan.due_on(today) or step_plan.step is None:
                continue
            if step_plan.step.escalates:
                self._log.add_event(
                    ReminderEvent(
                        tenant_id=tenant_id,
                        client_id=client.id,
                        outcome=Outcome.ESCALATED,
                        day=today,
                        created_at=now,
                        invoice_id=invoice.id,
                        step_id=step_plan.step.id,
                        offset_days=step_plan.step.offset_days,
                    )
                )
                escalated.append(invoice.id)
            elif client.whatsapp and not client.no_reminders:
                reminders[client.id].append(invoice.id)
        if escalated:
            self._queue.enqueue(escalation_email_job(tenant_id, escalated))

        if context.connection is not Connection.OK:
            # Paused: nothing goes out until WhatsApp is connected (or reconnected).
            return PlanResult(0, len(escalated), ended, context.connection.value)
        when = context.calendar.send_time(today, now)
        if when is None:
            return PlanResult(0, len(escalated), ended)
        already = self._log.clients_sent_on(tenant_id, today)
        sends = 0
        for client_id, invoice_ids in reminders.items():
            if client_id in already:
                continue  # at most one reminder per client per day
            queued = self._queue.enqueue(
                NewJob(
                    SEND_REMINDER_JOB,
                    {
                        "tenant_id": str(tenant_id),
                        "client_id": str(client_id),
                        "day": today.isoformat(),
                        "invoice_ids": [str(item) for item in invoice_ids],
                    },
                    run_at=when,
                    dedupe_key=f"reminder:{client_id}:{today.isoformat()}",
                )
            )
            sends += int(queued)
        logger.info(
            "reminders_planned",
            extra={"tenant_id": str(tenant_id), "sends": sends, "escalated": len(escalated)},
        )
        return PlanResult(sends, len(escalated), ended)


class PlanSweep:
    """Every morning: one planner job per active business. Each run schedules tomorrow's
    (the worker also enqueues today's when it starts; the dedupe keys keep it to one)."""

    def __init__(self, tenants: ActiveTenants, queue: JobQueue, clock: Clock = utc_now) -> None:
        self._tenants = tenants
        self._queue = queue
        self._clock = clock

    def __call__(self, job: Job) -> None:
        now = self._clock()
        for tenant_id in self._tenants():
            self._queue.enqueue(
                NewJob(
                    PLAN_JOB,
                    {"tenant_id": str(tenant_id)},
                    dedupe_key=f"reminder-plan:{tenant_id}:{now:%Y-%m-%d}",
                    max_attempts=5,
                )
            )
        tomorrow = datetime.combine(now.date() + timedelta(days=1), SWEEP_AT, now.tzinfo)
        self._queue.enqueue(sweep_job(tomorrow))
