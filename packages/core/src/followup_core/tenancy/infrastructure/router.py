from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..application.create_tenant import CreateTenant
from ..application.list_tenants import ListTenants
from ..domain.errors import (
    DuplicateTenantSlugError,
    InvalidTenantNameError,
    InvalidTenantSlugError,
)
from .repository import SqlAlchemyTenantRepository
from .schemas import TenantCreate, TenantRead

SessionDependency = Callable[..., Iterator[Session]]


def build_tenancy_router(get_session: SessionDependency) -> APIRouter:
    router = APIRouter(prefix="/tenants", tags=["tenants"])
    SessionDep = Annotated[Session, Depends(get_session)]

    def repository_for(session: Session) -> SqlAlchemyTenantRepository:
        return SqlAlchemyTenantRepository(session)

    @router.get("", response_model=list[TenantRead])
    def list_tenants(session: SessionDep) -> list[TenantRead]:
        tenants = ListTenants(repository_for(session)).execute()
        return [TenantRead.model_validate(tenant) for tenant in tenants]

    @router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
    def create_tenant(payload: TenantCreate, session: SessionDep) -> TenantRead:
        try:
            tenant = CreateTenant(repository_for(session)).execute(payload.name)
        except DuplicateTenantSlugError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe un negocio con ese nombre.",
            ) from error
        except (InvalidTenantNameError, InvalidTenantSlugError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="El nombre del negocio no es válido.",
            ) from error
        return TenantRead.model_validate(tenant)

    return router
