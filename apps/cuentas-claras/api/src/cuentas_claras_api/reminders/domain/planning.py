"""What comes next for one invoice, from its due date, the policy, what was already done for
it and today's date. Pure functions: the planner job, the send job and "Lo próximo" all ask
the same question here.

The step that matters is the latest one whose date has come (an invoice imported 10 days
overdue gets the "after" reminder, not the "3 days before" one first); earlier steps that
never went out are simply passed. Once it is done, the next one is the first step still
ahead. An invoice is never escalated before the client got at least one reminder: one
imported 60 days overdue gets the last reminder first, and is escalated after it (a client
who cannot get reminders is escalated right away).
Reminders wait for the next sending day; the escalation is an email to the owner, so it
does not wait for the send window.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from uuid import UUID

from .calendar import SendingCalendar
from .policy import ReminderPolicy, ReminderStep, TemplateKind, template_for_offset


@dataclass(frozen=True, slots=True)
class InvoiceState:
    """What planning needs to know about one owed invoice."""

    invoice_id: UUID
    client_id: UUID
    due_date: date
    promised_until: date | None = None


class Hold(StrEnum):
    """Why an invoice gets nothing right now."""

    PROMISED = "promised"  # the client promised to pay (and the policy pauses for it)
    ESCALATED = "escalated"  # the owner was told; reminders stopped
    FINISHED = "finished"  # every step is behind it (a policy without escalation)
    NO_STEPS = "no_steps"  # every step is turned off
    NO_SENDING_DAY = "no_sending_day"  # the window never opens (team hours on Saturdays)


@dataclass(frozen=True, slots=True)
class Plan:
    """The next step for an invoice and the day it is due (today or later)."""

    step: ReminderStep | None = None
    day: date | None = None
    hold: Hold | None = None
    # The promise's last day (Hold.PROMISED).
    until: date | None = None

    def due_on(self, today: date) -> bool:
        return self.step is not None and self.day is not None and self.day <= today


def target(state: InvoiceState, step: ReminderStep) -> date:
    return state.due_date + timedelta(days=step.offset_days)


def plan(
    state: InvoiceState,
    policy: ReminderPolicy,
    done: Collection[UUID],
    today: date,
    calendar: SendingCalendar,
    reachable: bool = True,
) -> Plan:
    """`done`: the steps already sent, failed for good or escalated for this invoice.
    `reachable`: the client can get reminders (a WhatsApp number, not opted out); one who
    cannot is escalated without waiting for a reminder."""
    steps = policy.active_steps
    if any(step.escalates and step.id in done for step in policy.steps):
        return Plan(hold=Hold.ESCALATED)
    if not steps:
        return Plan(hold=Hold.NO_STEPS)
    if (
        policy.pause_on_promise
        and state.promised_until is not None
        and state.promised_until >= today
    ):
        return Plan(hold=Hold.PROMISED, until=state.promised_until)

    reached = [step for step in steps if target(state, step) <= today]
    current = reached[-1] if reached else None
    if current is not None and current.escalates and current.id not in done:
        reminded = any(step.id in done for step in steps if not step.escalates)
        reminders = [step for step in reached if not step.escalates]
        if reachable and not reminded and reminders:
            current = reminders[-1]
    if current is not None and current.id not in done:
        return _when(current, today, calendar)
    ahead = [step for step in steps if target(state, step) > today and step.id not in done]
    if not ahead:
        return Plan(hold=Hold.FINISHED)
    return _when(ahead[0], target(state, ahead[0]), calendar)


def _when(step: ReminderStep, day: date, calendar: SendingCalendar) -> Plan:
    if step.escalates:
        return Plan(step=step, day=day)
    sending = calendar.next_sending_day(day)
    if sending is None:
        return Plan(hold=Hold.NO_SENDING_DAY)
    return Plan(step=step, day=sending)


def template_kind(step: ReminderStep, due_date: date, day: date) -> TemplateKind:
    """The step's template, unless it goes out on another day than planned (a weekend, a
    holiday, a promise that ended): then the text follows the real day, so a "due date"
    reminder sent three days late says it is overdue, never "hoy vence"."""
    assert step.template_kind is not None
    if due_date + timedelta(days=step.offset_days) == day:
        return step.template_kind
    return template_for_offset((day - due_date).days)


def postponed(plan_: Plan, today: date, calendar: SendingCalendar) -> Plan:
    """The same reminder moved past today (the client already got one today: at most one
    reminder per client per day)."""
    if plan_.step is None or plan_.step.escalates or not plan_.due_on(today):
        return plan_
    sending = calendar.next_sending_day(today + timedelta(days=1))
    if sending is None:
        return Plan(hold=Hold.NO_SENDING_DAY)
    return Plan(step=plan_.step, day=sending)
