from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from followup_core.tenancy.infrastructure.router import build_tenancy_router

from .config import get_settings
from .database import get_session

settings = get_settings()


def create_app() -> FastAPI:
    application = FastAPI(
        title="inmo24x7 API",
        description="API para agentes inmobiliarios de seguimiento.",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(build_tenancy_router(get_session))
    return application


app = create_app()
