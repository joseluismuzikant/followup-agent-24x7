"""The team's side of a lead (S6): take the conversation over, reply, give it back, and
confirm or cancel the visit. Each runs in one transaction; WhatsApp sending is a job
(`whatsapp.send`), so a Meta outage never rolls an action back."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from followup_core.conversation.application.control import (
    Actor,
    AddSystemEvent,
    AddTeamMessage,
    ReleaseThread,
    TakeOverThread,
)
from followup_core.conversation.application.ports import BusinessContextSource
from followup_core.conversation.application.threads import Clock, utc_now
from followup_core.conversation.domain.repositories import MessageRepository, ThreadRepository
from followup_core.conversation.domain.thread import Author, Channel, Message, Thread
from followup_core.messaging.domain.outbound import SERVICE_WINDOW, template_body
from followup_core.messaging.domain.repositories import ConnectionRepository

from ..domain.errors import (
    LeadNotFoundError,
    OutsideServiceWindowError,
    TemplateNotConfiguredError,
    VisitNotFoundError,
    VisitTimeInPastError,
)
from ..domain.lead import Lead, LeadStatus, Visit, VisitStatus
from ..domain.notices import cancelled_visit, confirmed_visit, visit_confirmation
from ..domain.repositories import LeadRepository

# Sends the team's messages on the lead's channel: WhatsApp queues them for the send job;
# the simulator shows them in its transcript, so there is nothing to send.
Deliver = Callable[[Thread, Sequence[Message]], None]
# The address of an own property, for the confirmation message.
PropertyAddress = Callable[[UUID, UUID], str | None]


@dataclass(frozen=True, slots=True)
class ServiceWindow:
    """WhatsApp only lets a business write freely for 24 hours after the lead's last
    message; after that, only an approved template."""

    expires_at: datetime | None

    def is_open(self, now: datetime) -> bool:
        return self.expires_at is not None and now < self.expires_at


def service_window(messages: Sequence[Message]) -> ServiceWindow:
    last = next(
        (message.created_at for message in reversed(messages) if message.author is Author.VISITOR),
        None,
    )
    return ServiceWindow(last + SERVICE_WINDOW if last else None)


class _LeadAction:
    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        clock: Clock = utc_now,
    ) -> None:
        self._leads = leads
        self._threads = threads
        self._messages = messages
        self._clock = clock

    def _lead(self, tenant_id: UUID, lead_id: UUID) -> tuple[Lead, Thread]:
        lead = self._leads.get(tenant_id, lead_id)
        thread = self._threads.get_by_id(lead.thread_id) if lead else None
        if lead is None or thread is None:
            raise LeadNotFoundError(str(lead_id))
        return lead, thread

    def _window_open(self, thread: Thread) -> bool:
        if thread.channel is not Channel.WHATSAPP:
            return True
        return service_window(self._messages.list_for_thread(thread.id)).is_open(self._clock())


class TakeOverLead(_LeadAction):
    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        take_over: TakeOverThread,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(leads, threads, messages, clock)
        self._take_over = take_over

    def execute(self, tenant_id: UUID, lead_id: UUID, actor: Actor) -> None:
        lead, thread = self._lead(tenant_id, lead_id)
        self._take_over.execute(thread.id, actor)
        self._leads.save(lead.touched(self._clock()))


class ReleaseLead(_LeadAction):
    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        release: ReleaseThread,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(leads, threads, messages, clock)
        self._release = release

    def execute(self, tenant_id: UUID, lead_id: UUID, actor: Actor) -> None:
        _, thread = self._lead(tenant_id, lead_id)
        self._release.execute(thread.id, actor)


class ReplyToLead(_LeadAction):
    """A message from the team. Only while the team controls the conversation; on WhatsApp,
    only inside the 24-hour window (nothing is stored otherwise)."""

    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        add_message: AddTeamMessage,
        deliver: Deliver,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(leads, threads, messages, clock)
        self._add_message = add_message
        self._deliver = deliver

    def execute(self, tenant_id: UUID, lead_id: UUID, actor: Actor, text: str) -> Message:
        lead, thread = self._lead(tenant_id, lead_id)
        if not self._window_open(thread):
            raise OutsideServiceWindowError(str(lead_id))
        message = self._add_message.execute(thread.id, actor, text)
        self._deliver(thread, [message])
        self._leads.save(lead.replied_by_team(message.created_at))
        return message


class _VisitAction(_LeadAction):
    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        add_message: AddTeamMessage,
        add_event: AddSystemEvent,
        deliver: Deliver,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(leads, threads, messages, clock)
        self._add_message = add_message
        self._add_event = add_event
        self._deliver = deliver

    def _visit(self, lead: Lead, visit_id: UUID) -> Visit:
        visit = next((item for item in self._leads.visits(lead.id) if item.id == visit_id), None)
        if visit is None:
            raise VisitNotFoundError(str(visit_id))
        return visit


class ConfirmVisit(_VisitAction):
    """Confirms (and optionally reschedules) the visit, moves the lead to visit_confirmed,
    writes the system event and tells the lead. Confirming again is a no-op."""

    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        add_message: AddTeamMessage,
        add_event: AddSystemEvent,
        deliver: Deliver,
        connections: ConnectionRepository,
        business: BusinessContextSource,
        property_address: PropertyAddress,
        clock: Clock = utc_now,
    ) -> None:
        super().__init__(leads, threads, messages, add_message, add_event, deliver, clock)
        self._connections = connections
        self._business = business
        self._property_address = property_address

    def execute(
        self,
        tenant_id: UUID,
        lead_id: UUID,
        visit_id: UUID,
        actor: Actor,
        starts_at: datetime | None = None,
    ) -> None:
        lead, thread = self._lead(tenant_id, lead_id)
        visit = self._visit(lead, visit_id)
        now = self._clock()
        if starts_at is not None and starts_at <= now:
            raise VisitTimeInPastError(str(visit_id))
        if visit.status is VisitStatus.CONFIRMED and starts_at in (None, visit.starts_at):
            return
        confirmed = visit.confirm(starts_at)

        # Decide how to tell the lead before writing anything: a missing template must
        # leave the visit, the lead and the transcript unchanged.
        local = confirmed.starts_at.astimezone(ZoneInfo(self._business(tenant_id).timezone))
        address = self._address(tenant_id, confirmed)
        notice = visit_confirmation(lead.visitor_name, address, local)
        payload = None
        if not self._window_open(thread):
            connection = self._connections.get_by_tenant(tenant_id)
            if connection is None or not connection.visit_template_name:
                raise TemplateNotConfiguredError(str(tenant_id))
            payload = {
                "template": template_body(
                    connection.visit_template_name,
                    connection.visit_template_language,
                    notice.template_parameters,
                )
            }

        self._leads.save_visit(confirmed)
        lead = lead.move_to(LeadStatus.VISIT_CONFIRMED, now)
        self._add_event.execute(thread.id, confirmed_visit(actor.name))
        message = self._add_message.execute(
            thread.id, actor, notice.text, require_control=False, payload=payload
        )
        self._deliver(thread, [message])
        self._leads.save(lead.replied_by_team(message.created_at))

    def _address(self, tenant_id: UUID, visit: Visit) -> str:
        if visit.property_id is not None:
            address = self._property_address(tenant_id, visit.property_id)
            if address:
                return address
        # Sample listings: "Monoambiente amoblado · Charcas 4100" → "Charcas 4100".
        return visit.property_label.split(" · ")[-1]


class CancelVisit(_VisitAction):
    """Cancels the visit and leaves the lead in human_requested for the team to follow up,
    optionally telling the lead why (free text: there is no cancellation template)."""

    def execute(
        self,
        tenant_id: UUID,
        lead_id: UUID,
        visit_id: UUID,
        actor: Actor,
        message: str | None = None,
    ) -> None:
        lead, thread = self._lead(tenant_id, lead_id)
        visit = self._visit(lead, visit_id)
        if visit.status is VisitStatus.CANCELLED:
            return
        text = (message or "").strip()
        if text and not self._window_open(thread):
            raise OutsideServiceWindowError(str(lead_id))
        now = self._clock()
        self._leads.save_visit(visit.cancel())
        lead = lead.move_to(LeadStatus.HUMAN_REQUESTED, now)
        self._add_event.execute(thread.id, cancelled_visit(actor.name))
        if text:
            sent = self._add_message.execute(thread.id, actor, text, require_control=False)
            self._deliver(thread, [sent])
            lead = lead.replied_by_team(sent.created_at)
        self._leads.save(lead.touched(now))


@dataclass(frozen=True, slots=True)
class LeadActions:
    """What the team can do on a lead, built per request by the container."""

    take_over: TakeOverLead
    release: ReleaseLead
    reply: ReplyToLead
    confirm: ConfirmVisit
    cancel: CancelVisit
