"""The Cuentas Claras API (port 8002 in development)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from followup_platform.health import build_health_router
from followup_platform.http_errors import register_error_handlers
from followup_platform.logging import configure_logging
from followup_platform.middleware import RequestContextMiddleware
from followup_platform.observability import init_sentry
from followup_platform.routers.account import build_account_router
from followup_platform.routers.admin_invitations import build_admin_invitations_router
from followup_platform.routers.me import build_me_router
from followup_platform.routers.onboarding import build_onboarding_router
from followup_platform.routers.tenant_settings import build_tenant_settings_router
from followup_platform.routers.webhooks import build_webhook_router
from followup_platform.routers.whatsapp import build_whatsapp_router
from followup_platform.whatsapp.errors import CUENTAS_CLARAS_COPY

from .auth import AUTH, require_platform_admin
from .backoffice.router import build_backoffice_router
from .clients.router import build_clients_router
from .config import get_settings
from .container import (
    admin_plan_audit,
    advance_onboarding_use_case,
    audit_log,
    backoffice_queries,
    cancel_invoice_use_case,
    client_invoices,
    create_business_use_case,
    create_client_use_case,
    create_invoice_use_case,
    embedded_signup_use_case,
    get_account_directory,
    get_client_use_case,
    get_clock,
    get_invoice_use_case,
    get_onboarding_use_case,
    get_tenant_settings_use_case,
    get_tenant_use_case,
    get_timezone_of,
    get_token_verifier,
    get_webhook_secrets,
    import_errors_use_case,
    import_invoices_use_case,
    ingest_webhook_use_case,
    invite_owner_use_case,
    list_clients_use_case,
    list_invoices_use_case,
    manage_connection_use_case,
    mark_paid_use_case,
    next_actions,
    payment_page_use_case,
    payment_settings,
    plan_reminders_use_case,
    promise_use_case,
    reconnect_link_use_case,
    reminder_events,
    reminder_settings_use_case,
    remove_promise_use_case,
    request_plan,
    request_template_sync,
    resend_invitation_use_case,
    reset_temporary_password_use_case,
    save_connection_use_case,
    save_policy_use_case,
    save_template_use_case,
    save_transfer_use_case,
    setup_checklist_dependency,
    sign_up_use_case,
    signup_state,
    summary_use_case,
    tenant_suspension_use_case,
    update_client_use_case,
    update_invoice_use_case,
    update_tenant_settings_use_case,
    webhook_counters,
)
from .database import get_session
from .invoices.router import build_invoices_router
from .payments.router import build_payments_router
from .product import DEFINITION, FACTS
from .reminders.router import build_reminders_router

LOGGER = "cuentas_claras.http"

configure_logging()
settings = get_settings()
init_sentry(settings, "cuentas-claras-api")
logger = logging.getLogger("cuentas_claras.app")


def utc_now() -> datetime:
    return datetime.now(UTC)


class CuentasRequestContextMiddleware(RequestContextMiddleware):
    logger_name = LOGGER


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Cuentas Claras API",
        description="API for Cuentas Claras: invoices, clients and collections.",
        version=settings.version,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(CuentasRequestContextMiddleware)
    register_error_handlers(application, logger_name=LOGGER)
    # Built once at startup so misconfiguration and the development warnings show early.
    get_token_verifier()

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
        build_tenant_settings_router(
            AUTH, DEFINITION, get_tenant_settings_use_case, update_tenant_settings_use_case
        )
    )
    application.include_router(
        build_clients_router(
            list_clients_use_case,
            get_client_use_case,
            create_client_use_case,
            update_client_use_case,
            client_invoices,
            get_timezone_of,
            lambda: get_clock()(),
        )
    )
    application.include_router(
        build_invoices_router(
            list_invoices_use_case,
            get_invoice_use_case,
            create_invoice_use_case,
            update_invoice_use_case,
            mark_paid_use_case,
            cancel_invoice_use_case,
            summary_use_case,
            import_invoices_use_case,
            import_errors_use_case,
            promise_use_case,
            remove_promise_use_case,
            next_actions,
            request_plan,
        )
    )
    application.include_router(
        build_webhook_router(
            ingest_webhook_use_case,
            get_webhook_secrets,
            webhook_counters,
            "cuentas_claras.webhooks",
        )
    )
    application.include_router(
        build_whatsapp_router(
            AUTH,
            save_connection_use_case,
            manage_connection_use_case,
            get_tenant_use_case,
            embedded_signup_use_case,
            signup_state,
            audit_log,
            reconnect_link_use_case,
            CUENTAS_CLARAS_COPY,
        )
    )
    application.include_router(
        build_reminders_router(
            reminder_settings_use_case,
            save_policy_use_case,
            save_template_use_case,
            plan_reminders_use_case,
            get_tenant_use_case,
            reminder_events,
            request_template_sync,
            admin_plan_audit,
        )
    )
    application.include_router(
        build_payments_router(
            payment_page_use_case, payment_settings, save_transfer_use_case, get_timezone_of
        )
    )
    application.include_router(
        build_backoffice_router(
            backoffice_queries,
            setup_checklist_dependency,
            tenant_suspension_use_case,
            utc_now,
            create_business_use_case,
            invite_owner_use_case,
        )
    )
    application.include_router(
        build_admin_invitations_router(
            require_platform_admin, resend_invitation_use_case, reset_temporary_password_use_case
        )
    )
    logger.info(
        "application_configured",
        extra={"app_env": settings.app_env, "version": settings.version},
    )
    return application


app = create_app()
