from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from ..application.create_tenant import CreateTenant
from ..application.list_tenants import ListTenants
from ..domain.errors import (
    DuplicateTenantSlugError,
    InvalidTenantNameError,
    InvalidTenantSlugError,
)
from .schemas import ErrorResponse, TenantCreate, TenantPageRead, TenantRead

CreateTenantFactory = Callable[..., CreateTenant]
ListTenantsFactory = Callable[..., ListTenants]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "Tenant slug already exists",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Invalid tenant data",
    },
}


def _error(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code})


def build_tenancy_router(
    create_tenant_factory: CreateTenantFactory,
    list_tenants_factory: ListTenantsFactory,
) -> APIRouter:
    router = APIRouter(prefix="/tenants", tags=["tenants"])

    @router.get(
        "",
        response_model=TenantPageRead,
        responses={status.HTTP_422_UNPROCESSABLE_CONTENT: ERROR_RESPONSES[422]},
    )
    def list_tenants(
        use_case: Annotated[ListTenants, Depends(list_tenants_factory)],
        page: Annotated[int, Query(ge=1)] = 1,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> TenantPageRead:
        result = use_case.execute(page=page, limit=limit)
        return TenantPageRead(
            items=[TenantRead.model_validate(tenant) for tenant in result.items],
            page=result.page,
            limit=result.limit,
            total=result.total,
            total_pages=result.total_pages,
        )

    @router.post(
        "",
        response_model=TenantRead,
        status_code=status.HTTP_201_CREATED,
        responses=ERROR_RESPONSES,
    )
    def create_tenant(
        payload: TenantCreate,
        use_case: Annotated[CreateTenant, Depends(create_tenant_factory)],
    ) -> TenantRead | JSONResponse:
        try:
            tenant = use_case.execute(payload.name)
        except DuplicateTenantSlugError:
            return _error(status.HTTP_409_CONFLICT, "tenant_slug_taken")
        except InvalidTenantNameError:
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "tenant_name_invalid",
            )
        except InvalidTenantSlugError:
            return _error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "tenant_slug_invalid",
            )
        return TenantRead.model_validate(tenant)

    return router
