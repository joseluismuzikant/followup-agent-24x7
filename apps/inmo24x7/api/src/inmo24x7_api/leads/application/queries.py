from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from followup_core.conversation.application.ports import AgentConfigSource
from followup_core.conversation.domain.repositories import MessageRepository, ThreadRepository
from followup_core.conversation.domain.thread import Message
from followup_core.tenancy.domain.agent_config import AgentConfig

from ..domain.errors import LeadNotFoundError
from ..domain.lead import Lead, Visit
from ..domain.repositories import LeadFilters, LeadPage, LeadRepository

PAGE_SIZE = 20


class ListLeads:
    def __init__(self, leads: LeadRepository) -> None:
        self._leads = leads

    def execute(self, tenant_id: UUID, filters: LeadFilters, page: int = 1) -> LeadPage:
        return self._leads.list(tenant_id, filters, max(page, 1), PAGE_SIZE)


@dataclass(frozen=True, slots=True)
class LeadDetail:
    lead: Lead
    visits: Sequence[Visit]
    # Lead, agent and system messages, read from the conversation tables.
    transcript: Sequence[Message]
    # The agent configuration the thread was pinned to, for the question labels.
    agent_config: AgentConfig


class GetLead:
    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        configs: AgentConfigSource,
    ) -> None:
        self._leads = leads
        self._threads = threads
        self._messages = messages
        self._configs = configs

    def execute(self, tenant_id: UUID, lead_id: UUID) -> LeadDetail:
        lead = self._leads.get(tenant_id, lead_id)
        if lead is None:
            raise LeadNotFoundError(str(lead_id))
        thread = self._threads.get_by_id(lead.thread_id)
        version = thread.agent_config_version if thread else self._configs.current(tenant_id)[0]
        return LeadDetail(
            lead=lead,
            visits=self._leads.visits(lead.id),
            transcript=self._messages.list_for_thread(lead.thread_id),
            agent_config=self._configs.at_version(tenant_id, version),
        )
