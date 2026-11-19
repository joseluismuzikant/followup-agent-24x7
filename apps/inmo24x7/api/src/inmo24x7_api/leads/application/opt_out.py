""" "BAJA" on the lead: what the inbox shows ("Pidió no ser contactado") and tells the team,
and the team's own "Marcar como no contactar" / "Quitar" for requests that arrive by email
or phone. The flag itself is core's (messaging/application/opt_out.py): the send job
enforces it for every message, whoever wrote it."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from followup_core.conversation.domain.thread import Channel, ThreadKey
from followup_core.messaging.application.opt_out import ContactOptOut
from followup_core.messaging.domain.opt_out import OptOutSource
from followup_core.scheduling.domain.jobs import JobQueue

from ..domain.errors import LeadNotFoundError, LeadNotOnWhatsAppError
from ..domain.repositories import LeadRepository
from .notify import opt_out_email_job

Clock = Callable[[], datetime]


class NotifyOptOut:
    """The WhatsApp pipeline's `on_opt_out`: the lead's activity moves to now and the team
    gets the lead email marked "Pidió no ser contactado". A "BAJA" from a number that never
    started a conversation has no lead: the flag is all there is."""

    def __init__(self, leads: LeadRepository, queue: JobQueue, clock: Clock) -> None:
        self._leads = leads
        self._queue = queue
        self._clock = clock

    def __call__(self, tenant_id: UUID, wa_id: str) -> None:
        lead = self._leads.get_by_thread_key(str(ThreadKey(tenant_id, Channel.WHATSAPP, wa_id)))
        if lead is None:
            return
        now = self._clock()
        self._leads.save(lead.touched(now))
        if not lead.is_test:
            self._queue.enqueue(opt_out_email_job(lead, now))


class SetLeadDoNotContact:
    """ "Marcar como no contactar" / "Quitar" on a WhatsApp lead, audited as the team's."""

    def __init__(self, leads: LeadRepository, opt_out: ContactOptOut) -> None:
        self._leads = leads
        self._opt_out = opt_out

    def execute(self, tenant_id: UUID, lead_id: UUID, profile_id: UUID, blocked: bool) -> None:
        lead = self._leads.get(tenant_id, lead_id)
        if lead is None:
            raise LeadNotFoundError(str(lead_id))
        wa_id = lead.wa_id
        if wa_id is None:
            raise LeadNotOnWhatsAppError(str(lead_id))
        if blocked:
            self._opt_out.block(
                tenant_id, wa_id, OptOutSource.TEAM, profile_id=profile_id, lead_id=lead.id
            )
        else:
            self._opt_out.lift(
                tenant_id, wa_id, OptOutSource.TEAM, profile_id=profile_id, lead_id=lead.id
            )
