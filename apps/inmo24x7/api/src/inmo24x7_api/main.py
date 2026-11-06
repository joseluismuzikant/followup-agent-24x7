import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from followup_core.conversation.application.threads import utc_now
from followup_core.tenancy.infrastructure.router import build_tenancy_router
from followup_platform.routers.account import build_account_router
from followup_platform.routers.admin_invitations import build_admin_invitations_router
from followup_platform.routers.me import build_me_router
from followup_platform.routers.onboarding import build_onboarding_router
from followup_platform.routers.tenant_settings import build_tenant_settings_router

from .agent_setup import build_agent_setup_router
from .auth import AUTH, require_platform_admin
from .backoffice.router import MonitoringLinks, build_backoffice_router
from .billing.router import build_usage_router
from .config import get_settings
from .container import (
    advance_onboarding_use_case,
    audit_log,
    backoffice_queries,
    create_business_use_case,
    create_property_use_case,
    create_tenant_use_case,
    delivery_statuses,
    embedded_signup_use_case,
    export_leads_use_case,
    get_account_directory,
    get_agent_setup_use_case,
    get_business_use_case,
    get_dashboard_use_case,
    get_language_model,
    get_lead_use_case,
    get_onboarding_use_case,
    get_sentry_issues,
    get_simulator_use_case,
    get_tenant_settings_use_case,
    get_tenant_use_case,
    get_token_verifier,
    get_trace_ui_url,
    get_tracing,
    get_webhook_secrets,
    has_published_properties,
    import_errors_use_case,
    import_properties_use_case,
    ingest_webhook_use_case,
    invite_owner_use_case,
    lead_actions,
    list_agent_versions_use_case,
    list_businesses_use_case,
    list_leads_use_case,
    list_properties_use_case,
    list_tenants_use_case,
    manage_connection_use_case,
    reconnect_link_use_case,
    resend_invitation_use_case,
    reset_simulator_use_case,
    reset_temporary_password_use_case,
    save_agent_setup_use_case,
    save_connection_use_case,
    send_simulator_message_use_case,
    set_property_status_use_case,
    sign_up_use_case,
    signup_state,
    tenant_suspension_use_case,
    tenant_usage_use_case,
    update_property_use_case,
    update_tenant_settings_use_case,
    usage_report_use_case,
    warn_if_model_unpriced,
    webhook_counters,
)
from .dashboard.router import build_dashboard_router
from .database import get_session
from .health import build_health_router
from .http_errors import register_error_handlers
from .leads.router import build_leads_router
from .logging import configure_logging
from .middleware import RequestContextMiddleware
from .observability import init_sentry
from .product import DEFINITION, FACTS
from .properties.router import build_properties_router
from .simulator import build_simulator_router
from .tracing import flush
from .webhooks import build_webhook_router
from .whatsapp import build_whatsapp_router

configure_logging()
settings = get_settings()
init_sentry(settings, "api")
logger = logging.getLogger("inmo24x7.app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    flush(get_tracing())  # send pending LangSmith runs before the process exits


def create_app() -> FastAPI:
    application = FastAPI(
        title="inmo24x7 API",
        description="API for real estate follow-up agents.",
        version=settings.version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # The panels show its first characters as "Código de referencia" on errors.
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestContextMiddleware)
    register_error_handlers(application)
    # Build once at startup so misconfiguration and the development warnings show early.
    get_token_verifier()
    get_language_model()
    get_tracing()
    warn_if_model_unpriced(settings)

    application.include_router(build_health_router(get_session, settings))
    application.include_router(
        build_me_router(
            AUTH,
            sign_up_use_case,
            get_tenant_use_case,
            settings.support_email,
        )
    )
    application.include_router(
        build_account_router(AUTH, get_session, get_settings, get_account_directory)
    )
    application.include_router(
        build_onboarding_router(
            AUTH, DEFINITION, FACTS, get_onboarding_use_case, advance_onboarding_use_case
        )
    )
    application.include_router(
        build_agent_setup_router(
            get_agent_setup_use_case,
            save_agent_setup_use_case,
            list_agent_versions_use_case,
        )
    )
    application.include_router(
        build_tenant_settings_router(
            AUTH,
            DEFINITION,
            get_tenant_settings_use_case,
            update_tenant_settings_use_case,
        )
    )
    application.include_router(
        build_simulator_router(
            get_simulator_use_case,
            send_simulator_message_use_case,
            reset_simulator_use_case,
            get_tenant_use_case,
            has_published_properties,
            get_trace_ui_url,
        )
    )
    application.include_router(
        build_properties_router(
            list_properties_use_case,
            create_property_use_case,
            update_property_use_case,
            set_property_status_use_case,
            import_properties_use_case,
            import_errors_use_case,
        )
    )
    application.include_router(
        build_leads_router(
            list_leads_use_case,
            get_lead_use_case,
            delivery_statuses,
            export_leads_use_case,
            lead_actions,
        )
    )
    application.include_router(build_dashboard_router(get_dashboard_use_case))
    application.include_router(
        build_webhook_router(ingest_webhook_use_case, get_webhook_secrets, webhook_counters)
    )
    application.include_router(
        build_whatsapp_router(
            save_connection_use_case,
            manage_connection_use_case,
            get_tenant_use_case,
            embedded_signup_use_case,
            signup_state,
            audit_log,
            reconnect_link_use_case,
        )
    )
    application.include_router(
        build_backoffice_router(
            list_businesses_use_case,
            get_business_use_case,
            create_business_use_case,
            invite_owner_use_case,
            tenant_suspension_use_case,
            backoffice_queries,
            (settings.version, settings.commit),
            utc_now,
            get_sentry_issues,
            MonitoringLinks(settings.grafana_url, settings.loki_datasource),
        )
    )
    application.include_router(
        build_admin_invitations_router(
            require_platform_admin, resend_invitation_use_case, reset_temporary_password_use_case
        )
    )
    application.include_router(
        build_usage_router(usage_report_use_case, tenant_usage_use_case, utc_now)
    )
    application.include_router(
        build_tenancy_router(
            create_tenant_use_case,
            list_tenants_use_case,
        ),
        dependencies=[Depends(require_platform_admin)],
    )

    if settings.rehearsal:
        logger.warning(
            "rehearsal_mode",
            extra={"detail": "Local production rehearsal: fake model and log sender."},
        )
    logger.info(
        "application_configured",
        extra={"app_env": settings.app_env, "version": settings.version},
    )
    return application


app = create_app()
