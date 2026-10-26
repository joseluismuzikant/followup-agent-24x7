import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from followup_core.tenancy.infrastructure.router import build_tenancy_router

from .config import get_settings
from .container import create_tenant_use_case, list_tenants_use_case
from .database import get_session
from .health import build_health_router
from .http_errors import register_error_handlers
from .logging import configure_logging
from .middleware import RequestContextMiddleware

configure_logging()
settings = get_settings()
logger = logging.getLogger("inmo24x7.app")


def create_app() -> FastAPI:
    application = FastAPI(
        title="inmo24x7 API",
        description="API for real estate follow-up agents.",
        version=settings.version,
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

    application.include_router(build_health_router(get_session, settings))
    application.include_router(
        build_tenancy_router(
            create_tenant_use_case,
            list_tenants_use_case,
        )
    )

    logger.info(
        "application_configured",
        extra={"app_env": settings.app_env, "version": settings.version},
    )
    return application


app = create_app()
