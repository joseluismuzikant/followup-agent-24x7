"""C4 "Recordatorios y cobros": the policy, each template with its Meta status, the
WhatsApp number and this month's count; saving the policy plans the business again."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from followup_core.messaging.domain.connection import WhatsAppConnection
from followup_core.scheduling.domain.jobs import JobQueue
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ...invoices.application.invoices import month_bounds
from ..domain.policy import ReminderPolicy, ReminderStep, SendWindow, TemplateKind
from ..domain.repositories import PolicyRepository, ReminderLog
from ..domain.templates import DEFAULT_BODIES, WhatsAppTemplate, in_use, newest
from .context import Clock, LoadContext, utc_now
from .planner import plan_now


@dataclass(frozen=True, slots=True)
class TemplateView:
    kind: TemplateKind
    # What C4 shows and edits: the newest version (maybe still in review).
    latest: WhatsAppTemplate | None
    # What goes out today (None: nothing approved yet).
    in_use: WhatsAppTemplate | None

    @property
    def body(self) -> str:
        return self.latest.body if self.latest else DEFAULT_BODIES[self.kind]


@dataclass(frozen=True, slots=True)
class ReminderSettings:
    policy: ReminderPolicy
    configured: bool
    templates: Sequence[TemplateView]
    whatsapp: WhatsAppConnection | None
    business_name: str
    month_count: int
    today: date
    upcoming_holidays: Sequence[date]


class GetReminderSettings:
    def __init__(
        self,
        load: LoadContext,
        policies: PolicyRepository,
        log: ReminderLog,
        clock: Clock = utc_now,
    ) -> None:
        self._load = load
        self._policies = policies
        self._log = log
        self._clock = clock

    def execute(self, tenant_id: UUID) -> ReminderSettings:
        context = self._load(tenant_id)
        today = context.calendar.today(self._clock())
        start, end = month_bounds(today)
        views = []
        for kind in TemplateKind:
            versions = [item for item in context.versions if item.kind is kind]
            views.append(TemplateView(kind, newest(versions), in_use(versions)))
        holidays = sorted(day for day in context.calendar.holidays if today <= day)[:5]
        return ReminderSettings(
            policy=context.policy,
            configured=self._policies.is_configured(tenant_id),
            templates=views,
            whatsapp=context.whatsapp,
            business_name=context.business_name,
            month_count=self._log.sent_count(tenant_id, start, end),
            today=today,
            upcoming_holidays=holidays,
        )


class SaveReminderPolicy:
    def __init__(
        self,
        policies: PolicyRepository,
        queue: JobQueue,
        audit: AuditLog,
        clock: Clock = utc_now,
    ) -> None:
        self._policies = policies
        self._queue = queue
        self._audit = audit
        self._clock = clock

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        steps: Sequence[ReminderStep],
        window: SendWindow,
        skip_holidays: bool,
        pause_on_promise: bool,
    ) -> ReminderPolicy:
        now = self._clock()
        current = self._policies.get(tenant_id) or ReminderPolicy.default(tenant_id)
        saved = current.with_changes(steps, window, skip_holidays, pause_on_promise, now)
        self._policies.save(saved, now)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER,
                CuentasAction.REMINDER_POLICY_SAVED,
                {"steps": str(len(saved.steps)), "window": saved.window.preset.value},
                actor_profile_id=profile_id,
            )
        )
        plan_now(self._queue, tenant_id, now)
        return saved


RequestPlan = Callable[[UUID], bool]
