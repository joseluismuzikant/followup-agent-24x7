"""Backoffice (platform admins only): S8 Negocios with KPIs and filters, "Dar de alta un
negocio", S9 Detalle del negocio with suspend / reactivate, Salud del sistema and Planes."""

from collections.abc import Callable
from datetime import datetime
from math import ceil
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from followup_core.identity.domain.profile import Profile
from followup_core.tenancy.application.admin_tenants import (
    CreateBusinessForOwner,
    SetTenantSuspension,
)
from followup_core.tenancy.domain.errors import (
    InvalidBusinessTypeError,
    InvalidSuspensionReasonError,
    InvalidTenantNameError,
    OwnerEmailTakenError,
    TenantNotFoundError,
)
from followup_core.tenancy.domain.plans import PLANS, plan_info
from pydantic import BaseModel, Field

from ..auth import require_platform_admin
from ..http_errors import ApiError
from ..whatsapp import WhatsAppConnectionRead, connection_read
from .application.overview import PAGE_SIZE, GetBusiness, ListBusinesses, TenantDetail
from .domain.rules import TenantFilter, TenantRow, mask, needs_help, whatsapp_badge
from .infrastructure.queries import SqlAlchemyBackofficeQueries

AdminDep = Annotated[Profile, Depends(require_platform_admin)]
Badge = Literal["connected", "verification_pending", "action_required", "not_connected"]
Clock = Callable[[], datetime]


class PlanRead(BaseModel):
    plan: Literal["trial", "pro"]
    name: str
    # "Prueba · N días"; null on a paid plan.
    trial_days_left: int | None


class OnboardingItemRead(BaseModel):
    key: Literal[
        "account", "agent_configured", "agent_tested", "whatsapp_connected", "own_properties"
    ]
    done: bool


class BusinessRowRead(BaseModel):
    id: UUID
    name: str
    status: Literal["active", "suspended"]
    owner_email: str | None
    # Created by an admin: the owner has not signed up yet.
    owner_pending: bool
    plan: PlanRead
    onboarding_done: int
    onboarding_total: int
    whatsapp: Badge
    needs_help: bool
    leads_last_7_days: int
    created_at: datetime


class KpisRead(BaseModel):
    active: int
    trial: int
    onboarding_unfinished: int
    whatsapp_problems: int


class BusinessListRead(BaseModel):
    items: list[BusinessRowRead]
    total: int
    page: int
    page_size: int
    kpis: KpisRead


class BusinessCreate(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    business_type: str = "inmobiliaria"
    owner_email: str = Field(max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserRead(BaseModel):
    id: UUID
    name: str
    email: str
    role: str


class ActivityRead(BaseModel):
    at: datetime
    actor_kind: Literal["user", "admin", "system"]
    actor_name: str | None
    action: str
    details: dict[str, str | int | bool | None]


class PlanUsageRead(BaseModel):
    conversations_this_month: int
    allowance: int
    users: int


class BusinessWhatsAppRead(WhatsAppConnectionRead):
    waba_masked: str | None = None


class BusinessDetailRead(BusinessRowRead):
    suspended_reason: str | None
    suspended_at: datetime | None
    onboarding: list[OnboardingItemRead]
    whatsapp_connection: BusinessWhatsAppRead
    usage: PlanUsageRead
    users: list[UserRead]
    activity: list[ActivityRead]


class SuspendWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class JobCountRead(BaseModel):
    kind: str
    status: str
    count: int


class FailedSendsRead(BaseModel):
    code: str
    count: int


class SystemRead(BaseModel):
    jobs: list[JobCountRead]
    dead_last_24h: int
    oldest_queued_seconds: float | None
    webhooks_last_hour: int
    signature_rejections_last_24h: int
    failed_sends_last_24h: list[FailedSendsRead]
    version: str
    commit: str
    database: Literal["ok", "unavailable"]


class PlanSummaryRead(BaseModel):
    plan: Literal["trial", "pro"]
    name: str
    monthly_conversations: int
    tenants: int


def _row_read(row: TenantRow, now: datetime) -> BusinessRowRead:
    days = None
    if row.plan == "trial":
        days = max(0, ceil((row.trial_ends_at - now).total_seconds() / 86_400))
    return BusinessRowRead(
        id=row.id,
        name=row.name,
        status="suspended" if row.suspended else "active",
        owner_email=row.owner_email,
        owner_pending=row.owner_pending,
        plan=PlanRead(
            plan="pro" if row.plan == "pro" else "trial",
            name="Pro" if row.plan == "pro" else "Prueba",
            trial_days_left=days,
        ),
        onboarding_done=row.onboarding.done,
        onboarding_total=len(row.onboarding.items),
        whatsapp=whatsapp_badge(row.whatsapp_status, row.business_verification).value,
        needs_help=needs_help(row, now),
        leads_last_7_days=row.leads_last_7_days,
        created_at=row.created_at,
    )


def _detail_read(detail: TenantDetail, now: datetime) -> BusinessDetailRead:
    connection = connection_read(detail.connection, detail.signup).model_dump()
    connection["waba_id"] = None  # masked below; the manual form reads its own endpoint
    connection["phone_number_id"] = None
    tenant = detail.tenant
    return BusinessDetailRead(
        **_row_read(detail.row, now).model_dump(),
        suspended_reason=tenant.suspended_reason,
        suspended_at=tenant.suspended_at,
        onboarding=[
            OnboardingItemRead(key=key, done=done)  # type: ignore[arg-type]
            for key, done in detail.row.onboarding.items
        ],
        whatsapp_connection=BusinessWhatsAppRead(
            **connection,
            waba_masked=mask(detail.connection.waba_id) if detail.connection else None,
        ),
        usage=PlanUsageRead(
            conversations_this_month=detail.conversations_this_month,
            allowance=detail.allowance,
            users=len(detail.users),
        ),
        users=[UserRead(id=u.id, name=u.name, email=u.email, role=u.role) for u in detail.users],
        activity=[
            ActivityRead(
                at=a.at,
                actor_kind=a.actor_kind,  # type: ignore[arg-type]
                actor_name=a.actor_name if a.actor_kind != "system" else None,
                action=a.action,
                details=a.details,
            )
            for a in detail.activity
        ],
    )


def build_backoffice_router(
    list_factory: Callable[..., ListBusinesses],
    detail_factory: Callable[..., GetBusiness],
    create_factory: Callable[..., CreateBusinessForOwner],
    suspension_factory: Callable[..., SetTenantSuspension],
    queries_factory: Callable[..., SqlAlchemyBackofficeQueries],
    version: tuple[str, str],
    clock: Clock,
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["backoffice"])

    def detail(get: GetBusiness, tenant_id: UUID) -> BusinessDetailRead:
        try:
            return _detail_read(get.execute(tenant_id), clock())
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

    @router.get("/tenants", response_model=BusinessListRead)
    def list_businesses(
        _admin: AdminDep,
        use_case: Annotated[ListBusinesses, Depends(list_factory)],
        filter: Annotated[TenantFilter, Query()] = TenantFilter.ALL,  # noqa: A002
        q: Annotated[str, Query(max_length=200)] = "",
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> BusinessListRead:
        result = use_case.execute(filter, q, page)
        now = clock()
        return BusinessListRead(
            items=[_row_read(row, now) for row in result.items],
            total=result.total,
            page=result.page,
            page_size=PAGE_SIZE,
            kpis=KpisRead(
                active=result.kpis.active,
                trial=result.kpis.trial,
                onboarding_unfinished=result.kpis.onboarding_unfinished,
                whatsapp_problems=result.kpis.whatsapp_problems,
            ),
        )

    @router.post(
        "/tenants", response_model=BusinessDetailRead, status_code=201, responses={409: {}}
    )
    def create_business(
        payload: BusinessCreate,
        admin: AdminDep,
        use_case: Annotated[CreateBusinessForOwner, Depends(create_factory)],
        get: Annotated[GetBusiness, Depends(detail_factory)],
    ) -> BusinessDetailRead:
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
        return detail(get, tenant.id)

    @router.get("/tenants/{tenant_id}", response_model=BusinessDetailRead)
    def get_business(
        tenant_id: UUID,
        _admin: AdminDep,
        get: Annotated[GetBusiness, Depends(detail_factory)],
    ) -> BusinessDetailRead:
        return detail(get, tenant_id)

    @router.post("/tenants/{tenant_id}/suspend", response_model=BusinessDetailRead)
    def suspend(
        tenant_id: UUID,
        payload: SuspendWrite,
        admin: AdminDep,
        use_case: Annotated[SetTenantSuspension, Depends(suspension_factory)],
        get: Annotated[GetBusiness, Depends(detail_factory)],
    ) -> BusinessDetailRead:
        try:
            use_case.suspend(admin.id, tenant_id, payload.reason)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        except InvalidSuspensionReasonError as error:
            raise ApiError(422, "suspension_reason_invalid") from error
        return detail(get, tenant_id)

    @router.post("/tenants/{tenant_id}/reactivate", response_model=BusinessDetailRead)
    def reactivate(
        tenant_id: UUID,
        admin: AdminDep,
        use_case: Annotated[SetTenantSuspension, Depends(suspension_factory)],
        get: Annotated[GetBusiness, Depends(detail_factory)],
    ) -> BusinessDetailRead:
        try:
            use_case.reactivate(admin.id, tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error
        return detail(get, tenant_id)

    @router.get("/system", response_model=SystemRead)
    def system(
        _admin: AdminDep,
        queries: Annotated[SqlAlchemyBackofficeQueries, Depends(queries_factory)],
    ) -> SystemRead:
        numbers = queries.system(clock())
        return SystemRead(
            jobs=[JobCountRead(kind=j.kind, status=j.status, count=j.count) for j in numbers.jobs],
            dead_last_24h=numbers.dead_last_24h,
            oldest_queued_seconds=numbers.oldest_queued_seconds,
            webhooks_last_hour=numbers.webhooks_last_hour,
            signature_rejections_last_24h=numbers.signature_rejections_last_24h,
            failed_sends_last_24h=[
                FailedSendsRead(code=code, count=count)
                for code, count in numbers.failed_sends_by_code
            ],
            version=version[0],
            commit=version[1],
            database="ok" if numbers.database_ok else "unavailable",
        )

    @router.get("/plans", response_model=list[PlanSummaryRead])
    def plans(
        _admin: AdminDep,
        queries: Annotated[SqlAlchemyBackofficeQueries, Depends(queries_factory)],
    ) -> list[PlanSummaryRead]:
        counts = queries.plan_counts()
        return [
            PlanSummaryRead(
                plan=item.plan.value,
                name=plan_info(item.plan).name,
                monthly_conversations=item.monthly_conversations,
                tenants=counts.get(item.plan.value, 0),
            )
            for item in PLANS
        ]

    return router
