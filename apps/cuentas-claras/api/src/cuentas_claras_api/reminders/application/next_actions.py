""" "Lo próximo" for a page of invoices (C2) or one invoice (the drawer)."""

from collections.abc import Sequence
from uuid import UUID

from ...invoices.domain.invoice import Invoice
from ..domain.next_action import NextAction, next_action
from ..domain.planning import InvoiceState, plan, postponed
from ..domain.repositories import OwedInvoices, ReminderLog
from .context import Clock, LoadContext, utc_now


class DescribeNextActions:
    def __init__(
        self, load: LoadContext, owed: OwedInvoices, log: ReminderLog, clock: Clock = utc_now
    ) -> None:
        self._load = load
        self._owed = owed
        self._log = log
        self._clock = clock

    def execute(self, tenant_id: UUID, invoices: Sequence[Invoice]) -> dict[UUID, NextAction]:
        """Only owed invoices get one (a paid or cancelled one has nothing next)."""
        owed = [invoice for invoice in invoices if invoice.is_open]
        if not owed:
            return {}
        now = self._clock()
        context = self._load(tenant_id)
        today = context.calendar.today(now)
        clients = self._owed.clients(tenant_id, list({invoice.client_id for invoice in owed}))
        done = self._log.done_steps(tenant_id, [invoice.id for invoice in owed])
        sent_today = self._log.clients_sent_on(tenant_id, today)
        approved = context.approved
        actions: dict[UUID, NextAction] = {}
        for invoice in owed:
            client = clients.get(invoice.client_id)
            state = InvoiceState(
                invoice.id, invoice.client_id, invoice.due_date, invoice.promised_until
            )
            reachable = bool(client and client.whatsapp and not client.no_reminders)
            step_plan = plan(
                state, context.policy, done[invoice.id], today, context.calendar, reachable
            )
            if invoice.client_id in sent_today:
                step_plan = postponed(step_plan, today, context.calendar)
            actions[invoice.id] = next_action(
                step_plan,
                due_date=invoice.due_date,
                has_whatsapp=bool(client and client.whatsapp),
                opted_out=bool(client and client.no_reminders),
                connection=context.connection,
                approved=approved,
                calendar=context.calendar,
                now=now,
            )
        return actions
