import logging
from collections.abc import Callable, Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import Settings

logger = logging.getLogger("inmo24x7.health")
SessionDependency = Callable[..., Iterator[Session]]


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]
    version: str
    commit: str
    build_date: str


class ReadinessError(BaseModel):
    code: Literal["database_unavailable"]


def build_health_router(get_session: SessionDependency, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/health", tags=["system"])

    @router.get("", response_model=LivenessResponse)
    def liveness() -> LivenessResponse:
        return LivenessResponse(status="ok")

    @router.get(
        "/ready",
        response_model=ReadinessResponse,
        responses={
            503: {
                "model": ReadinessError,
                "description": "Database unavailable",
            }
        },
    )
    def readiness(
        session: Annotated[Session, Depends(get_session)],
    ) -> ReadinessResponse | JSONResponse:
        try:
            session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            session.rollback()
            logger.exception("readiness_failed")
            return JSONResponse(
                status_code=503,
                content={"code": "database_unavailable"},
            )

        return ReadinessResponse(
            status="ready",
            database="ok",
            version=settings.version,
            commit=settings.commit,
            build_date=settings.build_date,
        )

    return router
