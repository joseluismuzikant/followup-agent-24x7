from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from followup_core.conversation.application.ports import AgentConfigSource, BusinessContextSource
from followup_core.conversation.domain.repositories import MessageRepository, ThreadRepository
from followup_core.conversation.domain.thread import Message, Thread
from followup_core.tenancy.domain.agent_config import AgentConfig

from ..domain.errors import LeadNotFoundError
from ..domain.lead import Lead, Visit
from ..domain.repositories import LeadFilters, LeadPage, LeadRepository

PAGE_SIZE = 25
EXPORT_LIMIT = 5000

# Display names of team members, by profile id (team messages and who has the conversation).
ProfileNames = Callable[[Sequence[UUID]], Mapping[UUID, str]]


class ListLeads:
    def __init__(self, leads: LeadRepository) -> None:
        self._leads = leads

    def execute(self, tenant_id: UUID, filters: LeadFilters, page: int = 1) -> LeadPage:
        return self._leads.list(tenant_id, filters, max(page, 1), PAGE_SIZE)


@dataclass(frozen=True, slots=True)
class LeadExport:
    leads: Sequence[Lead]
    latest_visits: Mapping[UUID, Visit]
    agent_config: AgentConfig
    # Dates are written in the business's timezone.
    timezone: str


class ExportLeads:
    """The rows of "Exportar CSV": the list's filters and order, up to 5,000 leads."""

    def __init__(
        self, leads: LeadRepository, configs: AgentConfigSource, business: BusinessContextSource
    ) -> None:
        self._leads = leads
        self._configs = configs
        self._business = business

    def execute(
        self, tenant_id: UUID, filters: LeadFilters, limit: int | None = None
    ) -> LeadExport:
        leads = self._leads.export(tenant_id, filters, limit or EXPORT_LIMIT)
        return LeadExport(
            leads=leads,
            latest_visits=self._leads.latest_visits([lead.id for lead in leads]),
            agent_config=self._configs.current(tenant_id)[1],
            timezone=self._business(tenant_id).timezone,
        )


@dataclass(frozen=True, slots=True)
class LeadDetail:
    lead: Lead
    visits: Sequence[Visit]
    # Lead, agent and system messages, read from the conversation tables.
    transcript: Sequence[Message]
    # The tenant's current agent configuration: the answers grid shows the questions the
    # business asks today, in its order (custom ones included).
    agent_config: AgentConfig
    thread: Thread | None = None
    # Names of the team members in the transcript and of who controls the conversation.
    names: Mapping[UUID, str] = field(default_factory=dict)


class GetLead:
    def __init__(
        self,
        leads: LeadRepository,
        threads: ThreadRepository,
        messages: MessageRepository,
        configs: AgentConfigSource,
        names: ProfileNames | None = None,
    ) -> None:
        self._leads = leads
        self._threads = threads
        self._messages = messages
        self._configs = configs
        self._names = names

    def execute(self, tenant_id: UUID, lead_id: UUID) -> LeadDetail:
        lead = self._leads.get(tenant_id, lead_id)
        if lead is None:
            raise LeadNotFoundError(str(lead_id))
        thread = self._threads.get_by_id(lead.thread_id)
        transcript = self._messages.list_for_thread(lead.thread_id)
        people = {m.author_profile_id for m in transcript if m.author_profile_id}
        if thread is not None and thread.controlled_by_profile_id:
            people.add(thread.controlled_by_profile_id)
        return LeadDetail(
            lead=lead,
            visits=self._leads.visits(lead.id),
            transcript=transcript,
            agent_config=self._configs.current(tenant_id)[1],
            thread=thread,
            names=self._names(sorted(people)) if self._names and people else {},
        )
