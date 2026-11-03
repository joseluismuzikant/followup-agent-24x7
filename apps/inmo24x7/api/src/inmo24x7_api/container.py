import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends
from followup_core.conversation.application.agent_config_source import (
    VersionedAgentConfigSource,
)
from followup_core.conversation.application.ports import BusinessContextSource
from followup_core.conversation.application.simulator import (
    GetSimulator,
    ResetSimulator,
    SendSimulatorMessage,
)
from followup_core.conversation.application.threads import (
    GetThread,
    HandleIncomingMessage,
    ReplyWithoutAgent,
    StartNewThread,
    utc_now,
)
from followup_core.conversation.domain.llm import LanguageModel
from followup_core.conversation.domain.runtime import BusinessContext
from followup_core.conversation.infrastructure.langgraph_runtime import (
    LangGraphRuntime,
    TurnTracing,
)
from followup_core.conversation.infrastructure.repositories import (
    PostgresAdvisoryThreadLock,
    SqlAlchemyConversationFacts,
    SqlAlchemyMessageRepository,
    SqlAlchemyThreadRepository,
)
from followup_core.identity.domain.token_verifier import TokenVerifier
from followup_core.identity.infrastructure.dev_verifier import DevTokenVerifier
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.identity.infrastructure.supabase_verifier import SupabaseJwtVerifier
from followup_core.messaging.application.connections import (
    ConnectionDefaults,
    GraphPort,
    ManageConnection,
    SaveConnection,
)
from followup_core.messaging.application.pipeline import (
    MARK_READ_JOB,
    PROCESS_JOB,
    PURGE_JOB,
    SEND_JOB,
    ApplyDeliveryStatus,
    IngestWebhook,
    MarkRead,
    ProcessInbound,
    PurgePayloads,
    SenderFor,
    SendQueued,
)
from followup_core.messaging.domain.connection import SenderKind, WhatsAppConnection
from followup_core.messaging.domain.outbound import WhatsAppSender
from followup_core.messaging.infrastructure.crypto import TokenCipher
from followup_core.messaging.infrastructure.graph import (
    CloudApiSender,
    CloudGraphPort,
    GraphClient,
    LogGraphPort,
)
from followup_core.messaging.infrastructure.log_sender import LOG_STATUS_JOB, LogSender
from followup_core.messaging.infrastructure.repositories import (
    SqlAlchemyConnectionRepository,
    SqlAlchemyInboundEventRepository,
    SqlAlchemyOutboundRepository,
)
from followup_core.notifications.domain.email import EmailSender
from followup_core.notifications.infrastructure.smtp import SmtpEmailSender, SmtpSettings
from followup_core.scheduling.domain.jobs import Job, JobHandlers, Reschedule
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.application.agent_setup import (
    GetAgentSetup,
    ListAgentConfigVersions,
    SaveAgentSetup,
)
from followup_core.tenancy.application.create_tenant import CreateTenant
from followup_core.tenancy.application.defaults import SetupDefaults
from followup_core.tenancy.application.get_setup_checklist import GetSetupChecklist
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.application.list_tenants import ListTenants
from followup_core.tenancy.application.onboarding_flow import AdvanceOnboarding, GetOnboarding
from followup_core.tenancy.application.setup_facts import SetupFactProviders
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.application.tenant_settings import (
    GetTenantSettings,
    UpdateTenantSettings,
)
from followup_core.tenancy.domain.errors import TenantNotFoundError
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyAgentConfigRepository,
    SqlAlchemyBusinessSettingsRepository,
    SqlAlchemyOnboardingRepository,
)
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .database import get_session
from .defaults import build_setup_defaults
from .leads.application.notify import (
    HANDOFF_EMAIL_JOB,
    IN_PROGRESS_EMAIL_JOB,
    SendLeadEmail,
)
from .leads.application.queries import GetLead, ListLeads
from .leads.application.record_turn import RecordLeadTurn
from .leads.graph import build_lead_graph
from .leads.infrastructure.repositories import SqlAlchemyLeadRepository
from .leads.llm import build_language_model
from .leads.tools import lead_tools
from .leads.whatsapp import LeadMessageRenderer
from .properties.application.properties import (
    CreateProperty,
    GetImportErrors,
    ImportProperties,
    ListProperties,
    SetPropertyStatus,
    UpdateProperty,
)
from .properties.infrastructure.repositories import (
    SqlAlchemyPropertyImportRepository,
    SqlAlchemyPropertyRepository,
    TenantPropertySearch,
)
from .properties.infrastructure.spreadsheet import read_spreadsheet
from .tracing import Tracing, build_tracing, turn_tracing

logger = logging.getLogger("inmo24x7.container")

SessionDep = Annotated[Session, Depends(get_session)]


def _issuer(supabase_url: str) -> str | None:
    return f"{supabase_url.rstrip('/')}/auth/v1" if supabase_url else None


@lru_cache
def get_token_verifier() -> TokenVerifier:
    settings = get_settings()
    if settings.auth_mode == "dev":
        logger.warning(
            "dev_auth_active",
            extra={"detail": "Only `dev:<email>` tokens are accepted. Development only."},
        )
        return DevTokenVerifier()
    return SupabaseJwtVerifier(
        secret=settings.supabase_jwt_secret or None,
        jwks_url=settings.supabase_jwks_url or None,
        issuer=_issuer(settings.supabase_url),
    )


def create_tenant_use_case(session: SessionDep) -> CreateTenant:
    return CreateTenant(SqlAlchemyTenantRepository(session))


def list_tenants_use_case(session: SessionDep) -> ListTenants:
    return ListTenants(SqlAlchemyTenantRepository(session))


def get_tenant_use_case(session: SessionDep) -> GetTenant:
    return GetTenant(SqlAlchemyTenantRepository(session))


@lru_cache
def get_setup_defaults() -> SetupDefaults:
    return build_setup_defaults()


def get_fact_providers(session: SessionDep) -> SetupFactProviders:
    """Later days plug their providers in here (WhatsApp, Meta)."""
    return SetupFactProviders(
        agent_tested=SqlAlchemyConversationFacts(session).agent_tested,
        # Done after the first import (or the first property added by hand).
        own_properties=SqlAlchemyPropertyRepository(session).has_any,
        whatsapp_connected=get_whatsapp_fact(session),
    )


def sign_up_use_case(session: SessionDep) -> SignUp:
    return SignUp(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyProfileRepository(session),
        SqlAlchemyOnboardingRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
        get_setup_defaults(),
    )


def setup_checklist_use_case(session: SessionDep) -> GetSetupChecklist:
    return GetSetupChecklist(SqlAlchemyAgentConfigRepository(session), get_fact_providers(session))


def get_onboarding_use_case(session: SessionDep) -> GetOnboarding:
    return GetOnboarding(SqlAlchemyOnboardingRepository(session), setup_checklist_use_case(session))


def advance_onboarding_use_case(session: SessionDep) -> AdvanceOnboarding:
    return AdvanceOnboarding(
        SqlAlchemyOnboardingRepository(session), setup_checklist_use_case(session)
    )


def get_agent_setup_use_case(session: SessionDep) -> GetAgentSetup:
    return GetAgentSetup(
        SqlAlchemyAgentConfigRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
        get_setup_defaults(),
    )


def save_agent_setup_use_case(session: SessionDep) -> SaveAgentSetup:
    return SaveAgentSetup(
        SqlAlchemyAgentConfigRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
        get_setup_defaults(),
    )


def list_agent_versions_use_case(session: SessionDep) -> ListAgentConfigVersions:
    return ListAgentConfigVersions(
        SqlAlchemyAgentConfigRepository(session),
        SqlAlchemyProfileRepository(session),
    )


def get_tenant_settings_use_case(session: SessionDep) -> GetTenantSettings:
    return GetTenantSettings(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
    )


def update_tenant_settings_use_case(session: SessionDep) -> UpdateTenantSettings:
    return UpdateTenantSettings(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
    )


@lru_cache
def get_language_model() -> LanguageModel:
    return build_language_model(get_settings())


@lru_cache
def get_lead_graph() -> StateGraph:
    return build_lead_graph()


@lru_cache
def get_tracing() -> Tracing | None:
    """The LangSmith client, built once (with the PII anonymizer); None when off."""
    return build_tracing(get_settings())


def get_turn_tracing() -> TurnTracing | None:
    return turn_tracing(get_tracing(), get_settings())


def get_trace_ui_url() -> str:
    tracing = get_tracing()
    return tracing.ui_url if tracing else ""


def agent_runtime(
    session: SessionDep,
    llm: Annotated[LanguageModel, Depends(get_language_model)],
    tracing: Annotated[TurnTracing | None, Depends(get_turn_tracing)],
) -> LangGraphRuntime:
    # The checkpointer writes on the request's own connection, inside its transaction, so the
    # transcript, the graph state and the thread lock commit or roll back together.
    connection = session.connection().connection.driver_connection
    if not isinstance(connection, psycopg.Connection):
        raise TypeError("The agent runtime needs a psycopg 3 connection.")
    tools = lead_tools(TenantPropertySearch(SqlAlchemyPropertyRepository(session)))
    return LangGraphRuntime(get_lead_graph(), PostgresSaver(connection), llm, tracing, tools)


RuntimeDep = Annotated[LangGraphRuntime, Depends(agent_runtime)]


def _business_context(session: Session) -> BusinessContextSource:
    tenants = SqlAlchemyTenantRepository(session)
    settings = SqlAlchemyBusinessSettingsRepository(session)

    def load(tenant_id: UUID) -> BusinessContext:
        tenant = tenants.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' does not exist.")
        tenant_settings = settings.get(tenant_id)
        if tenant_settings is None:
            defaults = get_setup_defaults()
            return BusinessContext(
                tenant_id, tenant.name, defaults.timezone, tuple(defaults.team_hours)
            )
        return BusinessContext(
            tenant_id=tenant_id,
            business_name=tenant.name,
            timezone=tenant_settings.timezone,
            team_hours=tenant_settings.team_hours,
        )

    return load


def _agent_configs(session: Session) -> VersionedAgentConfigSource:
    return VersionedAgentConfigSource(
        SqlAlchemyAgentConfigRepository(session), get_setup_defaults()
    )


def _get_thread(session: Session, runtime: LangGraphRuntime) -> GetThread:
    return GetThread(
        SqlAlchemyThreadRepository(session),
        SqlAlchemyMessageRepository(session),
        runtime,
        _agent_configs(session),
    )


def get_simulator_use_case(session: SessionDep, runtime: RuntimeDep) -> GetSimulator:
    return GetSimulator(SqlAlchemyThreadRepository(session), _get_thread(session, runtime))


def get_simulator_daily_limit() -> int:
    return get_settings().simulator_daily_limit


def send_simulator_message_use_case(
    session: SessionDep,
    runtime: RuntimeDep,
    daily_limit: Annotated[int, Depends(get_simulator_daily_limit)],
) -> SendSimulatorMessage:
    threads = SqlAlchemyThreadRepository(session)
    messages = SqlAlchemyMessageRepository(session)
    business = _business_context(session)
    handle = HandleIncomingMessage(
        threads,
        messages,
        PostgresAdvisoryThreadLock(session),
        runtime,
        _agent_configs(session),
        business,
        observers=[RecordLeadTurn(SqlAlchemyLeadRepository(session), SqlAlchemyJobQueue(session))],
    )
    return SendSimulatorMessage(threads, messages, handle, business, daily_limit)


def reset_simulator_use_case(session: SessionDep, runtime: RuntimeDep) -> ResetSimulator:
    threads = SqlAlchemyThreadRepository(session)
    start = StartNewThread(threads, PostgresAdvisoryThreadLock(session), _agent_configs(session))
    return ResetSimulator(threads, start, _get_thread(session, runtime))


def has_published_properties(session: SessionDep) -> Callable[[UUID], bool]:
    """False while the agent still shows the sample listings."""
    return SqlAlchemyPropertyRepository(session).has_published


def list_properties_use_case(session: SessionDep) -> ListProperties:
    return ListProperties(SqlAlchemyPropertyRepository(session))


def create_property_use_case(session: SessionDep) -> CreateProperty:
    return CreateProperty(SqlAlchemyPropertyRepository(session))


def update_property_use_case(session: SessionDep) -> UpdateProperty:
    return UpdateProperty(SqlAlchemyPropertyRepository(session))


def set_property_status_use_case(session: SessionDep) -> SetPropertyStatus:
    return SetPropertyStatus(SqlAlchemyPropertyRepository(session))


def import_properties_use_case(session: SessionDep) -> ImportProperties:
    return ImportProperties(
        SqlAlchemyPropertyRepository(session),
        SqlAlchemyPropertyImportRepository(session),
        read_spreadsheet,
    )


def import_errors_use_case(session: SessionDep) -> GetImportErrors:
    return GetImportErrors(SqlAlchemyPropertyImportRepository(session))


def list_leads_use_case(session: SessionDep) -> ListLeads:
    return ListLeads(SqlAlchemyLeadRepository(session))


def get_lead_use_case(session: SessionDep) -> GetLead:
    return GetLead(
        SqlAlchemyLeadRepository(session),
        SqlAlchemyThreadRepository(session),
        SqlAlchemyMessageRepository(session),
        _agent_configs(session),
    )


# --- Messaging (WhatsApp), jobs and email --------------------------------------------------


@dataclass(frozen=True)
class MessagingServices:
    """Process-wide clients, built once. Tests replace the whole bundle (fake Graph transport,
    recording email sender)."""

    settings: Settings
    cipher: TokenCipher
    graph: GraphClient
    email: EmailSender


@lru_cache
def get_messaging_services() -> MessagingServices:
    settings = get_settings()
    return MessagingServices(
        settings=settings,
        cipher=TokenCipher.from_setting(settings.token_encryption_key),
        graph=GraphClient(settings.meta_graph_base_url, settings.meta_graph_api_version),
        email=SmtpEmailSender(
            SmtpSettings(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                starttls=settings.smtp_starttls,
                sender=settings.email_from,
            )
        ),
    )


ServicesDep = Annotated[MessagingServices, Depends(get_messaging_services)]


def sender_for(services: MessagingServices, queue: SqlAlchemyJobQueue) -> SenderFor:
    """Each connection says how it sends: the Cloud API, or the log sender (development)."""

    def choose(connection: WhatsAppConnection) -> WhatsAppSender:
        if connection.sender is SenderKind.CLOUD:
            return CloudApiSender(services.graph, services.cipher)
        return LogSender(queue)

    return choose


def graph_for(services: MessagingServices) -> Callable[[WhatsAppConnection], GraphPort]:
    def choose(connection: WhatsAppConnection) -> GraphPort:
        if connection.sender is SenderKind.CLOUD:
            return CloudGraphPort(services.graph, services.cipher)
        return LogGraphPort()

    return choose


def ingest_webhook_use_case(session: SessionDep, services: ServicesDep) -> IngestWebhook:
    outbound = SqlAlchemyOutboundRepository(session)
    return IngestWebhook(
        SqlAlchemyConnectionRepository(session),
        SqlAlchemyInboundEventRepository(session),
        ApplyDeliveryStatus(outbound),
        SqlAlchemyJobQueue(session),
        timedelta(seconds=services.settings.inbound_debounce_seconds),
    )


def get_webhook_secrets(services: ServicesDep) -> tuple[str, str]:
    """(META_APP_SECRET, WHATSAPP_VERIFY_TOKEN)."""
    return services.settings.meta_app_secret, services.settings.whatsapp_verify_token


def save_connection_use_case(session: SessionDep, services: ServicesDep) -> SaveConnection:
    settings = services.settings
    return SaveConnection(
        SqlAlchemyConnectionRepository(session),
        services.cipher.encrypt,
        ConnectionDefaults(
            sender=SenderKind(settings.whatsapp_sender),
            template_name=settings.whatsapp_default_template,
            template_language=settings.whatsapp_default_template_language,
        ),
    )


def manage_connection_use_case(session: SessionDep, services: ServicesDep) -> ManageConnection:
    return ManageConnection(
        SqlAlchemyConnectionRepository(session),
        graph_for(services),
        sender_for(services, SqlAlchemyJobQueue(session)),
    )


def delivery_statuses(session: SessionDep) -> SqlAlchemyOutboundRepository:
    return SqlAlchemyOutboundRepository(session)


def job_handlers(
    session: Session,
    services: MessagingServices,
    llm: LanguageModel,
    tracing: TurnTracing | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> JobHandlers:
    """Every job kind and its one handler (the worker builds this per job, on the job's
    own session and transaction)."""
    settings = services.settings
    queue = SqlAlchemyJobQueue(session, clock)
    connections = SqlAlchemyConnectionRepository(session)
    events = SqlAlchemyInboundEventRepository(session)
    outbound = SqlAlchemyOutboundRepository(session)
    threads = SqlAlchemyThreadRepository(session)
    messages = SqlAlchemyMessageRepository(session)
    lock = PostgresAdvisoryThreadLock(session)
    choose_sender = sender_for(services, queue)
    debounce = timedelta(seconds=settings.inbound_debounce_seconds)

    def process(job: Job) -> Reschedule | None:
        # Built per job: the agent runtime needs this session's connection.
        handle = HandleIncomingMessage(
            threads,
            messages,
            lock,
            agent_runtime(session, llm, tracing),
            _agent_configs(session),
            _business_context(session),
            observers=[RecordLeadTurn(SqlAlchemyLeadRepository(session), queue)],
        )
        return ProcessInbound(
            events,
            connections,
            outbound,
            lock,
            handle,
            ReplyWithoutAgent(threads, messages, lock, _agent_configs(session)),
            LeadMessageRenderer(settings.panel_url),
            queue,
            debounce,
            clock,
        )(job)

    statuses = ApplyDeliveryStatus(outbound)

    def log_status(job: Job) -> None:
        """The log sender's simulated sent / delivered / read, through Meta's code path."""
        statuses.execute(job.payload["wamid"], job.payload["status"], clock())

    lead_email = SendLeadEmail(
        get_lead_use_case(session),
        SqlAlchemyBusinessSettingsRepository(session),
        services.email,
        settings.panel_url,
    )
    return JobHandlers(
        [
            (PROCESS_JOB, process),
            (SEND_JOB, SendQueued(outbound, connections, choose_sender, clock)),
            (MARK_READ_JOB, MarkRead(connections, choose_sender)),
            (PURGE_JOB, PurgePayloads(events, queue, clock)),
            (LOG_STATUS_JOB, log_status),
            (HANDOFF_EMAIL_JOB, lead_email),
            (IN_PROGRESS_EMAIL_JOB, lead_email),
        ]
    )


def get_whatsapp_fact(session: Session) -> Callable[[UUID], bool]:
    def connected(tenant_id: UUID) -> bool:
        connection = SqlAlchemyConnectionRepository(session).get_by_tenant(tenant_id)
        return connection is not None and connection.is_connected

    return connected
