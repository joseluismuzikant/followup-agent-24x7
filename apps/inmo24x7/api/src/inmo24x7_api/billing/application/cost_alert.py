"""LLM_MONTHLY_COST_ALERT_USD: a daily job emails SUPPORT_EMAIL once per business and month
when its LLM cost reaches the limit, and records it in the business's activity."""

import html
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from followup_core.notifications.domain.email import Email, EmailError, EmailSender
from followup_core.scheduling.domain.jobs import Job, JobError, JobQueue, NewJob
from followup_core.tenancy.domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog

from ..domain.usage import Month
from ..infrastructure.queries import SqlAlchemyUsageQueries

COST_ALERT_JOB = "billing.cost_alert"

logger = logging.getLogger("inmo24x7.billing")

Clock = Callable[[], datetime]


def cost_alert_job(day: datetime, run_at: datetime | None = None) -> NewJob:
    """One per UTC day, whoever enqueues it (the worker at start, or the previous run)."""
    return NewJob(
        COST_ALERT_JOB,
        {},
        run_at=run_at,
        dedupe_key=f"llm-cost-alert:{day:%Y-%m-%d}",
        max_attempts=3,
    )


def dedupe_key(tenant_id: object, month: Month) -> str:
    return f"llm_cost_alert:{tenant_id}:{month}"


class CheckCostAlerts:
    def __init__(
        self,
        queries: SqlAlchemyUsageQueries,
        audit: AuditLog,
        sender: EmailSender,
        support_email: str,
        limit: Decimal | None,
        queue: JobQueue,
        clock: Clock,
    ) -> None:
        self._queries = queries
        self._audit = audit
        self._sender = sender
        self._support_email = support_email
        self._limit = limit
        self._queue = queue
        self._clock = clock

    def __call__(self, job: Job) -> None:
        now = self._clock()
        tomorrow = (now + timedelta(days=1)).replace(hour=6, minute=0, second=0, microsecond=0)
        self._queue.enqueue(cost_alert_job(tomorrow, run_at=tomorrow))
        if self._limit is None:
            return
        month = Month.of(now)
        alerted = 0
        for tenant_id, name, cost in self._queries.over_limit(month, self._limit):
            # The event and the email share the job's transaction: a failed email rolls the
            # event back, and the next attempt tries both again.
            self._audit.record(
                AuditEvent(
                    tenant_id,
                    now,
                    ActorKind.SYSTEM,
                    AuditAction.LLM_COST_ALERT,
                    {"month": str(month), "cost_usd": f"{cost:.2f}"},
                    dedupe_key=dedupe_key(tenant_id, month),
                )
            )
            self._send(tenant_id, name, cost, month)
            alerted += 1
        logger.info("llm_cost_alerts", extra={"alerted": alerted, "month": str(month)})

    def _send(self, tenant_id: object, name: str, cost: Decimal, month: Month) -> None:
        limit = f"{self._limit:.2f}"
        where = f"Backoffice → Consumo → {month} (negocio {tenant_id})"
        text = (
            f"{name} lleva USD {cost:.2f} de LLM en {month} (UTC), por encima del aviso de "
            f"USD {limit}.\n\nDetalle: {where}\n\n— inmo24x7"
        )
        body = (
            f"<p>{html.escape(name)} lleva <strong>USD {cost:.2f}</strong> de LLM en {month} "
            f"(UTC), por encima del aviso de USD {limit}.</p>"
            f"<p>Detalle: {html.escape(where)}</p><p>— inmo24x7</p>"
        )
        try:
            self._sender.send(
                Email(
                    to=[self._support_email],
                    subject=f"Consumo de LLM alto: {name}",
                    text=text,
                    html=body,
                )
            )
        except EmailError as error:
            raise JobError(f"email_{error.code}") from error
