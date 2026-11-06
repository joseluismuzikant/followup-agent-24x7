"""The Cuentas Claras backoffice (platform admins only): Negocios (only this product's
businesses), "Dar de alta un negocio" (the business, its owner's account and the invitation)
and the business detail with suspend / reactivate. C5 comes on Day 11."""

from collections.abc import Callable
from datetime import datetime
from math import ceil
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from followup_core.identity.application.accounts import InviteOwner
from followup_core.identity.domain.profile import Profile
from followup_core.tenancy.application.admin_tenants import (
    CreateBusinessForOwner,
    SetTenantSuspension,
)
from followup_core.tenancy.application.get_setup_checklist import GetSetupChecklist
from followup_core.tenancy.domain.errors import (
    InvalidBusinessTypeError,
    InvalidSuspensionReasonError,
    InvalidTenantNameError,
    OwnerEmailTakenError,
    TenantNotFoundError,
)
from followup_core.tenancy.domain.tenant import Plan
from followup_platform.http_errors import ApiError
from followup_platform.routers.admin_invitations import invite_new_owner
from pydantic import BaseModel, Field

from ..auth import require_platform_admin
from ..product import DEFINITION
from .infrastructure.queries import BusinessRow, SqlAlchemyCuentasBackofficeQueries

AdminDep = Annotated[Profile, Depends(require_platform_admin)]
PAGE_SIZE = 20


class PlanRead(BaseModel):
    plan: Literal["trial", "pro"]
    # "Prueba · N días" in the backoffice; null on a paid plan.
    trial_days_left: int | None


class BusinessRowRead(BaseModel):
    id: UUID
    name: str
    status: Literal["active", "suspended"]
    owner_email: str | None
    owner_pending: bool
    plan: PlanRead
    onboarding_done: int
    onboarding_total: int
    clients: int
    # ARS still to collect (open invoices), a decimal string.
    open_amount: str
    created_at: datetime


class BusinessListRead(BaseModel):
    items: list[BusinessRowRead]
    total: int
    page: int
    page_size: int


class ChecklistItemRead(BaseModel):
    key: str
    done: bool


class ActivityRead(BaseModel):
    at: datetime
    actor_kind: Literal["user", "admin", "system"]
    actor_name: str | None
    action: str
    details: dict[str, Any]


class BusinessDetailRead(BusinessRowRead):
    suspended_reason: str | None
    checklist: list[ChecklistItemRead]
    activity: list[ActivityRead]


class BusinessCreatedRead(BusinessDetailRead):
    # The owner's temporary password, shown once; null when they already had an account.
    temporary_password: str | None


class BusinessCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    business_type: str = "mantenimiento"
    owner_email: str = Field(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SuspendWrite(BaseModel):
    reason: str = Field(max_length=500)


def build_backoffice_router(
    queries_factory: Callable[..., SqlAlchemyCuentasBackofficeQueries],
    checklist_factory: Callable[..., GetSetupChecklist],
    suspension_factory: Callable[..., SetTenantSuspension],
    clock: Callable[[], datetime],
    create_factory: Callable[..., CreateBusinessForOwner],
    invite_factory: Callable[..., InviteOwner],
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["backoffice"])

    def row_read(row: BusinessRow, done: int) -> dict[str, Any]:
        plan = Plan(row.plan)
        days = None
        if plan is Plan.TRIAL:
            days = max(0, ceil((row.trial_ends_at - clock()).total_seconds() / 86_400))
        return {
            "id": row.id,
            "name": row.name,
            "status": "suspended" if row.suspended else "active",
            "owner_email": row.owner_email,
            "owner_pending": row.owner_pending,
            "plan": PlanRead(plan=plan.value, trial_days_left=days),  # type: ignore[arg-type]
            "onboarding_done": done,
            "onboarding_total": len(DEFINITION.checklist),
            "clients": row.clients,
            "open_amount": f"{row.open_amount:.2f}",
            "created_at": row.created_at,
        }

    def detail(
        queries: SqlAlchemyCuentasBackofficeQueries, checklist: GetSetupChecklist, tenant_id: UUID
    ) -> BusinessDetailRead:
        rows = queries.businesses(tenant_id=tenant_id)
        if not rows:
            raise ApiError(404, "tenant_not_found")
        items = checklist.execute(tenant_id)
        return BusinessDetailRead(
            **row_read(rows[0], items.ready_count),
            suspended_reason=rows[0].suspended_reason,
            checklist=[ChecklistItemRead(key=item.key, done=item.done) for item in items.items],
            activity=[
                ActivityRead(
                    at=event.at,
                    actor_kind=event.actor_kind,  # type: ignore[arg-type]
                    actor_name=event.actor_name if event.actor_kind != "system" else None,
                    action=event.action,
                    details=event.details,
                )
                for event in queries.activity(tenant_id)
            ],
        )

    @router.get("/tenants", response_model=BusinessListRead)
    def list_businesses(
        _admin: AdminDep,
        queries: Annotated[SqlAlchemyCuentasBackofficeQueries, Depends(queries_factory)],
        q: Annotated[str, Query(max_length=200)] = "",
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> BusinessListRead:
        rows = queries.businesses(q)
        shown = rows[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        return BusinessListRead(
            # The checklist's "N de 5": the account, plus invoices loaded (the rest is Day 9).
            items=[BusinessRowRead(**row_read(row, 1 + row.invoices_loaded)) for row in shown],
            total=len(rows),
            page=page,
            page_size=PAGE_SIZE,
        )

    @router.post(
        "/tenants",
        response_model=BusinessCreatedRead,
        status_code=201,
        responses={409: {}, 422: {}, 503: {}},
    )
    def create_business(
        payload: BusinessCreate,
        admin: AdminDep,
        use_case: Annotated[CreateBusinessForOwner, Depends(create_factory)],
        invite: Annotated[InviteOwner, Depends(invite_factory)],
        queries: Annotated[SqlAlchemyCuentasBackofficeQueries, Depends(queries_factory)],
        checklist: Annotated[GetSetupChecklist, Depends(checklist_factory)],
    ) -> BusinessCreatedRead:
        try:
            tenant = use_case.execute(
                admin.id, payload.business_name, payload.business_type, payload.owner_email
            )
        except OwnerEmailTakenError as error:
            raise ApiError(409, "owner_email_taken") from error
        except InvalidBusinessTypeError as error:
            raise ApiError(422, "business_type_invalid") from error
        except InvalidTenantNameError as error:
            raise ApiError(422, "tenant_name_invalid") from error
        password = invite_new_owner(invite, admin.id, tenant.id)
        return BusinessCreatedRead(
            **detail(queries, checklist, tenant.id).model_dump(), temporary_password=password
        )

    @router.get("/tenants/{tenant_id}", response_model=BusinessDetailRead)
    def get_business(
        tenant_id: UUID,
        _admin: AdminDep,
        queries: Annotated[SqlAlchemyCuentasBackofficeQueries, Depends(queries_factory)],
        checklist: Annotated[GetSetupChecklist, Depends(checklist_factory)],
    ) -> BusinessDetailRead:
        return detail(queries, checklist, tenant_id)

    @router.post("/tenants/{tenant_id}/suspend", response_model=BusinessDetailRead)
    def suspend(
        tenant_id: UUID,
        payload: SuspendWrite,
        admin: AdminDep,
        use_case: Annotated[SetTenantSuspension, Depends(suspension_factory)],
        queries: Annotated[SqlAlchemyCuentasBackofficeQueries, Depends(queries_factory)],
        checklist: Annotated[GetSetupChecklist, Depends(checklist_factory)],
    ) -> BusinessDetailRead:
        try:
            use_case.suspend(admin.id, tenant_id, payload.reason)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        except InvalidSuspensionReasonError as error:
            raise ApiError(422, "suspension_reason_invalid") from error
        return detail(queries, checklist, tenant_id)

    @router.post("/tenants/{tenant_id}/reactivate", response_model=BusinessDetailRead)
    def reactivate(
        tenant_id: UUID,
        admin: AdminDep,
        use_case: Annotated[SetTenantSuspension, Depends(suspension_factory)],
        queries: Annotated[SqlAlchemyCuentasBackofficeQueries, Depends(queries_factory)],
        checklist: Annotated[GetSetupChecklist, Depends(checklist_factory)],
    ) -> BusinessDetailRead:
        try:
            use_case.reactivate(admin.id, tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        return detail(queries, checklist, tenant_id)

    return router
