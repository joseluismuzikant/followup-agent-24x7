import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import Depends
from followup_core.conversation.application.agent_config_source import (
    VersionedAgentConfigSource,
)
from followup_core.conversation.application.control import (
    AddSystemEvent,
    AddTeamMessage,
    ReleaseThread,
    TakeOverThread,
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
from followup_core.conversation.domain.thread import Channel, Message, Thread
from followup_core.conversation.domain.usage import LlmUsageRecorder
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
from followup_core.conversation.infrastructure.usage import SqlAlchemyLlmUsageRecorder
from followup_core.identity.application.accounts import (
    INVITATION_EMAIL_JOB,
    InviteOwner,
    ResendInvitation,
    ResetTemporaryPassword,
)
from followup_core.identity.domain.account import AccountDirectory
from followup_core.identity.domain.token_verifier import TokenVerifier
from followup_core.identity.infrastructure.models import ProfileModel
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.messaging.application.connections import (
    ConnectionDefaults,
    GraphPort,
    ManageConnection,
    SaveConnection,
)
from followup_core.messaging.application.health import (
    ConnectionHealth,
)
from followup_core.messaging.application.pipeline import (
    PROCESS_JOB,
    PURGE_JOB,
    IngestWebhook,
    ProcessInbound,
    PurgePayloads,
    QueueOutbound,
    SenderFor,
)
from followup_core.messaging.application.reconnect import AGENT_STOPPED
from followup_core.messaging.application.signup import CompleteEmbeddedSignup
from followup_core.messaging.domain.connection import (
    BusinessVerification,
    WhatsAppConnection,
)
from followup_core.messaging.domain.signup import Signup
from followup_core.messaging.infrastructure.repositories import (
    SqlAlchemyConnectionRepository,
    SqlAlchemyInboundEventRepository,
    SqlAlchemyOutboundRepository,
    SqlAlchemySignupRepository,
    SqlAlchemyWebhookCounters,
)
from followup_core.scheduling.domain.jobs import Job, JobHandlers, Reschedule
from followup_core.scheduling.infrastructure.queue import SqlAlchemyJobQueue
from followup_core.tenancy.application.admin_tenants import (
    CreateBusinessForOwner,
    SetTenantSuspension,
)
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
from followup_core.tenancy.application.setup_facts import FactProvider, always
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.application.tenant_settings import (
    GetTenantSettings,
    UpdateTenantSettings,
)
from followup_core.tenancy.domain.audit import AuditLog
from followup_core.tenancy.domain.errors import TenantNotFoundError
from followup_core.tenancy.infrastructure.audit_repository import (
    SqlAlchemyAuditLog,
    SqlAlchemyOwnerClaimRepository,
)
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from followup_core.tenancy.infrastructure.setup_repositories import (
    SqlAlchemyAgentConfigRepository,
    SqlAlchemyBusinessSettingsRepository,
    SqlAlchemyOnboardingRepository,
)
from followup_platform import invitations
from followup_platform.identity import build_account_directory, build_token_verifier
from followup_platform.whatsapp import wiring
from followup_platform.whatsapp.wiring import MessagingServices
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session

from .backoffice.application.overview import GetBusiness, ListBusinesses
from .backoffice.infrastructure.queries import SqlAlchemyBackofficeQueries
from .backoffice.infrastructure.sentry_issues import SentryIssuesClient
from .billing.application.cost_alert import COST_ALERT_JOB, CheckCostAlerts
from .billing.application.usage import GetTenantUsage, GetUsageReport
from .billing.infrastructure.prices import load_prices
from .billing.infrastructure.queries import SqlAlchemyUsageQueries
from .config import Settings, get_settings
from .dashboard.application.get_dashboard import GetDashboard
from .dashboard.infrastructure.queries import SqlAlchemyDashboardQueries
from .database import UsageSessionLocal, get_session
from .defaults import build_setup_defaults
from .leads.application.inbox import (
    CancelVisit,
    ConfirmVisit,
    LeadActions,
    ReleaseLead,
    ReplyToLead,
    TakeOverLead,
)
from .leads.application.notify import (
    HANDOFF_EMAIL_JOB,
    IN_PROGRESS_EMAIL_JOB,
    SendLeadEmail,
)
from .leads.application.queries import ExportLeads, GetLead, ListLeads, ProfileNames
from .leads.application.record_turn import RecordLeadTurn
from .leads.graph import build_lead_graph
from .leads.infrastructure.repositories import SqlAlchemyLeadRepository
from .leads.llm import build_language_model
from .leads.tools import lead_tools
from .leads.whatsapp import LeadMessageRenderer
from .product import DEFINITION, PRODUCT
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


@lru_cache
def get_token_verifier() -> TokenVerifier:
    return build_token_verifier(get_settings())


def get_account_directory(session: SessionDep) -> AccountDirectory:
    """Where passwords live: Supabase Auth, or the local table in AUTH_MODE=dev."""
    return build_account_directory(get_settings(), session)


AccountDirectoryDep = Annotated[AccountDirectory, Depends(get_account_directory)]


def create_tenant_use_case(session: SessionDep) -> CreateTenant:
    return CreateTenant(SqlAlchemyTenantRepository(session, PRODUCT))


def list_tenants_use_case(session: SessionDep) -> ListTenants:
    return ListTenants(SqlAlchemyTenantRepository(session, PRODUCT))


def get_tenant_use_case(session: SessionDep) -> GetTenant:
    return GetTenant(SqlAlchemyTenantRepository(session, PRODUCT))


@lru_cache
def get_setup_defaults() -> SetupDefaults:
    return build_setup_defaults()


def get_fact_providers(session: SessionDep) -> dict[str, FactProvider]:
    """inmo24x7's setup facts (product.FACTS), one provider each."""
    agent_configs = SqlAlchemyAgentConfigRepository(session)
    return {
        "account_created": always,
        "agent_configured": lambda tenant_id: agent_configs.latest(tenant_id) is not None,
        "agent_tested": SqlAlchemyConversationFacts(session).agent_tested,
        "whatsapp_connected": get_whatsapp_fact(session),
        # Done after the first import (or the first property added by hand).
        "own_properties": SqlAlchemyPropertyRepository(session).has_any,
        "meta_business_verified": get_meta_verified_fact(session),
    }


def sign_up_use_case(session: SessionDep) -> SignUp:
    return SignUp(
        SqlAlchemyProfileRepository(session, PRODUCT),
        SqlAlchemyTenantRepository(session, PRODUCT),
        SqlAlchemyOwnerClaimRepository(session, PRODUCT),
        SqlAlchemyAuditLog(session),
        definition=DEFINITION,
    )


def invite_owner_use_case(session: SessionDep, directory: AccountDirectoryDep) -> InviteOwner:
    return invitations.invite_owner(session, PRODUCT, directory)


def resend_invitation_use_case(session: SessionDep) -> ResendInvitation:
    return invitations.resend_invitation(session, PRODUCT)


def reset_temporary_password_use_case(
    session: SessionDep, directory: AccountDirectoryDep
) -> ResetTemporaryPassword:
    return invitations.reset_temporary_password(session, PRODUCT, directory)


def create_business_use_case(session: SessionDep) -> CreateBusinessForOwner:
    return CreateBusinessForOwner(
        SqlAlchemyTenantRepository(session, PRODUCT),
        SqlAlchemyProfileRepository(session, PRODUCT),
        SqlAlchemyOnboardingRepository(session),
        SqlAlchemyBusinessSettingsRepository(session),
        SqlAlchemyOwnerClaimRepository(session, PRODUCT),
        get_setup_defaults(),
        SqlAlchemyAuditLog(session),
        definition=DEFINITION,
    )


def tenant_suspension_use_case(session: SessionDep) -> SetTenantSuspension:
    return SetTenantSuspension(
        SqlAlchemyTenantRepository(session, PRODUCT), SqlAlchemyAuditLog(session)
    )


def setup_checklist_use_case(session: SessionDep) -> GetSetupChecklist:
    return GetSetupChecklist(DEFINITION.checklist, get_fact_providers(session))


def get_onboarding_use_case(session: SessionDep) -> GetOnboarding:
    return GetOnboarding(SqlAlchemyOnboardingRepository(session), setup_checklist_use_case(session))


def advance_onboarding_use_case(session: SessionDep) -> AdvanceOnboarding:
    return AdvanceOnboarding(
        SqlAlchemyOnboardingRepository(session),
        setup_checklist_use_case(session),
        DEFINITION.onboarding_steps,
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
        SqlAlchemyAuditLog(session),
    )


def list_agent_versions_use_case(session: SessionDep) -> ListAgentConfigVersions:
    return ListAgentConfigVersions(
        SqlAlchemyAgentConfigRepository(session),
        SqlAlchemyProfileRepository(session, PRODUCT),
    )


def get_tenant_settings_use_case(session: SessionDep) -> GetTenantSettings:
    return GetTenantSettings(
        SqlAlchemyTenantRepository(session, PRODUCT),
        SqlAlchemyBusinessSettingsRepository(session),
    )


def update_tenant_settings_use_case(session: SessionDep) -> UpdateTenantSettings:
    return UpdateTenantSettings(
        SqlAlchemyTenantRepository(session, PRODUCT),
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


@lru_cache
def get_usage_recorder() -> LlmUsageRecorder:
    """Every model call, on its own connection (see database.usage_engine)."""
    return SqlAlchemyLlmUsageRecorder(UsageSessionLocal, load_prices())


def warn_if_model_unpriced(settings: Settings) -> None:
    """A model without a price still works; its calls just have no cost on Consumo."""
    if settings.llm_model and not load_prices().has_model(settings.llm_model):
        logger.warning(
            "llm_model_unpriced",
            extra={
                "model": settings.llm_model,
                "detail": "Add its price to llm_prices.toml (followup_platform); costs stay empty.",
            },
        )


def agent_runtime(
    session: SessionDep,
    llm: Annotated[LanguageModel, Depends(get_language_model)],
    tracing: Annotated[TurnTracing | None, Depends(get_turn_tracing)],
    usage: Annotated[LlmUsageRecorder | None, Depends(get_usage_recorder)],
) -> LangGraphRuntime:
    # The checkpointer writes on the request's own connection, inside its transaction, so the
    # transcript, the graph state and the thread lock commit or roll back together.
    connection = session.connection().connection.driver_connection
    if not isinstance(connection, psycopg.Connection):
        raise TypeError("The agent runtime needs a psycopg 3 connection.")
    tools = lead_tools(TenantPropertySearch(SqlAlchemyPropertyRepository(session)))
    return LangGraphRuntime(get_lead_graph(), PostgresSaver(connection), llm, tracing, tools, usage)


RuntimeDep = Annotated[LangGraphRuntime, Depends(agent_runtime)]


def _business_context(session: Session) -> BusinessContextSource:
    tenants = SqlAlchemyTenantRepository(session, PRODUCT)
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
        observers=[
            RecordLeadTurn(
                SqlAlchemyLeadRepository(session), SqlAlchemyJobQueue(session, queue=PRODUCT)
            )
        ],
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
        audit=SqlAlchemyAuditLog(session),
    )


def import_errors_use_case(session: SessionDep) -> GetImportErrors:
    return GetImportErrors(SqlAlchemyPropertyImportRepository(session))


def list_leads_use_case(session: SessionDep) -> ListLeads:
    return ListLeads(SqlAlchemyLeadRepository(session))


def _profile_names(session: Session) -> ProfileNames:
    def names(profile_ids: Sequence[UUID]) -> Mapping[UUID, str]:
        rows = session.execute(
            select(ProfileModel.id, ProfileModel.display_name, ProfileModel.email).where(
                ProfileModel.id.in_(profile_ids)
            )
        )
        return {row.id: (row.display_name or "").strip() or row.email for row in rows}

    return names


def get_lead_use_case(session: SessionDep) -> GetLead:
    return GetLead(
        SqlAlchemyLeadRepository(session),
        SqlAlchemyThreadRepository(session),
        SqlAlchemyMessageRepository(session),
        _agent_configs(session),
        _profile_names(session),
    )


def get_dashboard_use_case(session: SessionDep) -> GetDashboard:
    return GetDashboard(
        SqlAlchemyDashboardQueries(session),
        SqlAlchemyLeadRepository(session),
        _business_context(session),
        _agent_configs(session),
    )


def export_leads_use_case(session: SessionDep) -> ExportLeads:
    return ExportLeads(
        SqlAlchemyLeadRepository(session), _agent_configs(session), _business_context(session)
    )


# --- Messaging (WhatsApp), jobs and email --------------------------------------------------


@lru_cache
def get_messaging_services() -> MessagingServices:
    return wiring.build_messaging_services(get_settings())


ServicesDep = Annotated[MessagingServices, Depends(get_messaging_services)]


def sender_for(services: MessagingServices, queue: SqlAlchemyJobQueue) -> SenderFor:
    return wiring.sender_for(services, queue)


def graph_for(services: MessagingServices) -> Callable[[WhatsAppConnection], GraphPort]:
    return wiring.graph_for(services)


def ingest_webhook_use_case(session: SessionDep, services: ServicesDep) -> IngestWebhook:
    return wiring.ingest_webhook(session, services, PRODUCT)


def webhook_counters(session: SessionDep) -> SqlAlchemyWebhookCounters:
    return SqlAlchemyWebhookCounters(session)


def get_webhook_secrets(services: ServicesDep) -> tuple[str, str]:
    """(META_APP_SECRET, WHATSAPP_VERIFY_TOKEN)."""
    return wiring.webhook_secrets(services)


def save_connection_use_case(session: SessionDep, services: ServicesDep) -> SaveConnection:
    return wiring.save_connection(session, services, PRODUCT)


def manage_connection_use_case(session: SessionDep, services: ServicesDep) -> ManageConnection:
    return wiring.manage_connection(session, services, PRODUCT)


def connection_defaults(settings: Settings) -> ConnectionDefaults:
    return wiring.connection_defaults(settings)


def connection_health(
    session: Session, clock: Callable[[], datetime] = utc_now
) -> ConnectionHealth:
    return wiring.connection_health(session, PRODUCT, clock)


def embedded_signup_use_case(session: SessionDep, services: ServicesDep) -> CompleteEmbeddedSignup:
    return wiring.embedded_signup(session, services, PRODUCT)


def signup_state(session: SessionDep) -> Callable[[UUID], Signup | None]:
    return wiring.signup_state(session)


def audit_log(session: SessionDep) -> AuditLog:
    return SqlAlchemyAuditLog(session)


def tenant_is_active(session: Session) -> Callable[[UUID], bool]:
    """False for a suspended business: no agent replies, emails or scheduled checks."""
    return wiring.tenant_is_active(session)


def owner_emails(session: Session) -> Callable[[UUID], Sequence[str]]:
    return wiring.owner_emails(session)


def business_name(session: Session) -> Callable[[UUID], str]:
    return wiring.business_name(session)


def reconnect_link_use_case(session: SessionDep) -> Callable[[UUID, UUID], int]:
    return wiring.reconnect_link(session, PRODUCT)


def delivery_statuses(session: SessionDep) -> SqlAlchemyOutboundRepository:
    return SqlAlchemyOutboundRepository(session)


def job_handlers(
    session: Session,
    services: MessagingServices,
    llm: LanguageModel,
    tracing: TurnTracing | None = None,
    clock: Callable[[], datetime] = utc_now,
    usage: LlmUsageRecorder | None = None,
) -> JobHandlers:
    """Every job kind and its one handler (the worker builds this per job, on the job's
    own session and transaction)."""
    settings = services.settings
    queue = SqlAlchemyJobQueue(session, clock, PRODUCT)
    connections = SqlAlchemyConnectionRepository(session, PRODUCT)
    events = SqlAlchemyInboundEventRepository(session)
    outbound = SqlAlchemyOutboundRepository(session)
    threads = SqlAlchemyThreadRepository(session)
    messages = SqlAlchemyMessageRepository(session)
    lock = PostgresAdvisoryThreadLock(session)
    debounce = timedelta(seconds=settings.inbound_debounce_seconds)
    is_active = tenant_is_active(session)

    def process(job: Job) -> Reschedule | None:
        # Built per job: the agent runtime needs this session's connection.
        handle = HandleIncomingMessage(
            threads,
            messages,
            lock,
            agent_runtime(session, llm, tracing, usage),
            _agent_configs(session),
            _business_context(session),
            clock=clock,
            observers=[RecordLeadTurn(SqlAlchemyLeadRepository(session), queue)],
        )
        return ProcessInbound(
            events,
            connections,
            outbound,
            lock,
            handle,
            ReplyWithoutAgent(threads, messages, lock, _agent_configs(session), clock),
            LeadMessageRenderer(settings.panel_url),
            queue,
            debounce,
            clock,
            is_active,
        )(job)

    lead_email = SendLeadEmail(
        get_lead_use_case(session),
        SqlAlchemyBusinessSettingsRepository(session),
        services.email,
        settings.panel_url,
        is_active,
    )
    return JobHandlers(
        [
            (PROCESS_JOB, process),
            *wiring.whatsapp_job_handlers(
                session,
                services,
                PRODUCT,
                product_name="inmo24x7",
                stopped=AGENT_STOPPED,
                clock=clock,
            ),
            (PURGE_JOB, PurgePayloads(events, queue, clock)),
            (
                INVITATION_EMAIL_JOB,
                invitations.invitation_email_handler(
                    session, PRODUCT, services.email, "inmo24x7", settings.panel_url
                ),
            ),
            (
                COST_ALERT_JOB,
                CheckCostAlerts(
                    SqlAlchemyUsageQueries(session),
                    SqlAlchemyAuditLog(session),
                    services.email,
                    settings.support_email,
                    settings.llm_monthly_cost_alert_usd,
                    queue,
                    clock,
                ),
            ),
            (HANDOFF_EMAIL_JOB, lead_email),
            (IN_PROGRESS_EMAIL_JOB, lead_email),
        ]
    )


def _deliver(
    session: Session, settings: Settings, clock: Callable[[], datetime] = utc_now
) -> Callable[[Thread, Sequence[Message]], None]:
    """The team's messages on the lead's channel. WhatsApp: queued for the send job. The
    simulator shows them in its transcript; nothing is sent."""
    queue_outbound = QueueOutbound(
        SqlAlchemyOutboundRepository(session),
        LeadMessageRenderer(settings.panel_url),
        SqlAlchemyJobQueue(session, clock, PRODUCT),
    )

    def deliver(thread: Thread, messages: Sequence[Message]) -> None:
        if thread.channel is Channel.WHATSAPP:
            queue_outbound(messages, thread.visitor_id)

    return deliver


def build_lead_actions(
    session: Session, settings: Settings, clock: Callable[[], datetime] = utc_now
) -> LeadActions:
    leads = SqlAlchemyLeadRepository(session)
    threads = SqlAlchemyThreadRepository(session)
    messages = SqlAlchemyMessageRepository(session)
    lock = PostgresAdvisoryThreadLock(session)
    add_message = AddTeamMessage(threads, messages, lock, clock)
    add_event = AddSystemEvent(threads, messages, lock, clock)
    deliver = _deliver(session, settings, clock)
    properties = SqlAlchemyPropertyRepository(session)

    def address(tenant_id: UUID, property_id: UUID) -> str | None:
        found = properties.get(tenant_id, property_id)
        return found.fields.address if found else None

    return LeadActions(
        take_over=TakeOverLead(
            leads, threads, messages, TakeOverThread(threads, messages, lock, clock), clock
        ),
        release=ReleaseLead(
            leads, threads, messages, ReleaseThread(threads, messages, lock, clock), clock
        ),
        reply=ReplyToLead(leads, threads, messages, add_message, deliver, clock),
        confirm=ConfirmVisit(
            leads,
            threads,
            messages,
            add_message,
            add_event,
            deliver,
            SqlAlchemyConnectionRepository(session),
            _business_context(session),
            address,
            clock,
        ),
        cancel=CancelVisit(leads, threads, messages, add_message, add_event, deliver, clock),
    )


def lead_actions(session: SessionDep, services: ServicesDep) -> LeadActions:
    """The team's actions on a lead (S6), per request."""
    return build_lead_actions(session, services.settings)


def usage_report_use_case(session: SessionDep) -> GetUsageReport:
    return GetUsageReport(SqlAlchemyUsageQueries(session))


def tenant_usage_use_case(session: SessionDep) -> GetTenantUsage:
    return GetTenantUsage(SqlAlchemyUsageQueries(session))


@lru_cache
def get_sentry_issues() -> SentryIssuesClient:
    """Built once: its one-minute cache is per process."""
    settings = get_settings()
    return SentryIssuesClient(
        settings.sentry_api_url,
        settings.sentry_api_token,
        settings.sentry_org,
        settings.sentry_projects,
    )


def backoffice_queries(session: SessionDep) -> SqlAlchemyBackofficeQueries:
    return SqlAlchemyBackofficeQueries(session)


def list_businesses_use_case(session: SessionDep) -> ListBusinesses:
    return ListBusinesses(SqlAlchemyBackofficeQueries(session), utc_now)


def get_business_use_case(session: SessionDep) -> GetBusiness:
    return GetBusiness(
        SqlAlchemyBackofficeQueries(session),
        SqlAlchemyTenantRepository(session, PRODUCT).get_by_id,
        SqlAlchemyConnectionRepository(session).get_by_tenant,
        SqlAlchemySignupRepository(session).get,
        utc_now,
    )


def get_meta_verified_fact(session: Session) -> Callable[[UUID], bool]:
    def verified(tenant_id: UUID) -> bool:
        connection = SqlAlchemyConnectionRepository(session).get_by_tenant(tenant_id)
        return (
            connection is not None
            and connection.business_verification is BusinessVerification.VERIFIED
        )

    return verified


def get_whatsapp_fact(session: Session) -> Callable[[UUID], bool]:
    def connected(tenant_id: UUID) -> bool:
        connection = SqlAlchemyConnectionRepository(session).get_by_tenant(tenant_id)
        return connection is not None and connection.is_connected

    return connected
