import logging
from collections.abc import Callable
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
    StartNewThread,
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
from followup_core.identity.domain.token_verifier import TokenVerifier, VerifiedToken
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.identity.infrastructure.supabase_verifier import (
    FakeTokenVerifier,
    SupabaseJwtVerifier,
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
from followup_core.tenancy.application.setup_facts import SetupFactProviders
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.application.tenant_settings import (
    GetTenantSettings,
    UpdateTenantSettings,
)
from followup_core.tenancy.domain.business_settings import DEFAULT_TIMEZONE
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

from .config import get_settings
from .database import get_session
from .defaults import build_setup_defaults
from .leads.graph import build_lead_graph
from .leads.llm import build_language_model
from .leads.properties import PropertySearch, SamplePropertySearch
from .tracing import Tracing, build_tracing, turn_tracing

logger = logging.getLogger("inmo24x7.container")

SessionDep = Annotated[Session, Depends(get_session)]


def _issuer(supabase_url: str) -> str | None:
    return f"{supabase_url.rstrip('/')}/auth/v1" if supabase_url else None


@lru_cache
def get_token_verifier() -> TokenVerifier:
    settings = get_settings()
    if settings.supabase_jwt_secret or settings.supabase_jwks_url:
        return SupabaseJwtVerifier(
            secret=settings.supabase_jwt_secret or None,
            jwks_url=settings.supabase_jwks_url or None,
            issuer=_issuer(settings.supabase_url),
        )
    logger.warning(
        "fake_token_verifier_active",
        extra={"detail": "Any bearer token is accepted. Development only."},
    )
    return FakeTokenVerifier(
        default=VerifiedToken(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            email="dev@example.com",
        )
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
    """Later days plug their providers in here (properties, WhatsApp, Meta)."""
    return SetupFactProviders(agent_tested=SqlAlchemyConversationFacts(session).agent_tested)


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
def get_property_search() -> PropertySearch:
    """Sample listings until Day 4 adds the tenant's own properties."""
    return SamplePropertySearch()


@lru_cache
def get_lead_graph() -> StateGraph:
    return build_lead_graph(get_property_search())


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
    return LangGraphRuntime(get_lead_graph(), PostgresSaver(connection), llm, tracing)


RuntimeDep = Annotated[LangGraphRuntime, Depends(agent_runtime)]


def _business_context(session: Session) -> BusinessContextSource:
    tenants = SqlAlchemyTenantRepository(session)
    settings = SqlAlchemyBusinessSettingsRepository(session)

    def load(tenant_id: UUID) -> BusinessContext:
        tenant = tenants.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant '{tenant_id}' does not exist.")
        tenant_settings = settings.get(tenant_id)
        return BusinessContext(
            tenant_id=tenant_id,
            business_name=tenant.name,
            timezone=tenant_settings.timezone if tenant_settings else DEFAULT_TIMEZONE,
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
    )
    return SendSimulatorMessage(threads, messages, handle, business, daily_limit)


def reset_simulator_use_case(session: SessionDep, runtime: RuntimeDep) -> ResetSimulator:
    threads = SqlAlchemyThreadRepository(session)
    start = StartNewThread(threads, PostgresAdvisoryThreadLock(session), _agent_configs(session))
    return ResetSimulator(threads, start, _get_thread(session, runtime))


def own_properties_fact(session: SessionDep) -> Callable[[UUID], bool]:
    return get_fact_providers(session).own_properties
