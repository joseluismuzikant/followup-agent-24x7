import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from followup_core.tenancy.infrastructure.router import build_tenancy_router

from .agent_setup import build_agent_setup_router
from .auth import require_platform_admin
from .config import get_settings
from .container import (
    advance_onboarding_use_case,
    create_tenant_use_case,
    get_agent_setup_use_case,
    get_language_model,
    get_onboarding_use_case,
    get_simulator_use_case,
    get_tenant_settings_use_case,
    get_tenant_use_case,
    get_token_verifier,
    get_trace_ui_url,
    get_tracing,
    list_agent_versions_use_case,
    list_tenants_use_case,
    own_properties_fact,
    reset_simulator_use_case,
    save_agent_setup_use_case,
    send_simulator_message_use_case,
    sign_up_use_case,
    update_tenant_settings_use_case,
)
from .database import get_session
from .health import build_health_router
from .http_errors import register_error_handlers
from .logging import configure_logging
from .me import build_me_router
from .middleware import RequestContextMiddleware
from .onboarding import build_onboarding_router
from .simulator import build_simulator_router
from .tenant_settings import build_tenant_settings_router
from .tracing import flush

configure_logging()
settings = get_settings()
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
    )
    application.add_middleware(RequestContextMiddleware)
    register_error_handlers(application)
    # Build once at startup so misconfiguration and the development warnings show early.
    get_token_verifier()
    get_language_model()
    get_tracing()

    application.include_router(build_health_router(get_session, settings))
    application.include_router(
        build_me_router(
            sign_up_use_case,
            get_tenant_use_case,
        )
    )
    application.include_router(
        build_onboarding_router(get_onboarding_use_case, advance_onboarding_use_case)
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
            own_properties_fact,
            get_trace_ui_url,
        )
    )
    application.include_router(
        build_tenancy_router(
            create_tenant_use_case,
            list_tenants_use_case,
        ),
        dependencies=[Depends(require_platform_admin)],
    )

    logger.info(
        "application_configured",
        extra={"app_env": settings.app_env, "version": settings.version},
    )
    return application


app = create_app()
