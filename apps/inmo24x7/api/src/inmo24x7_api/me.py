from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from followup_core.identity.domain.profile import Profile
from followup_core.identity.domain.token_verifier import VerifiedToken
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.domain.errors import (
    DuplicateTenantSlugError,
    InvalidBusinessTypeError,
    InvalidTenantNameError,
    InvalidTenantSlugError,
    TenantNotFoundError,
)
from followup_core.tenancy.domain.tenant import Tenant
from pydantic import BaseModel, Field

from .auth import current_identity, current_profile
from .http_errors import ApiError

SignUpFactory = Callable[..., SignUp]
GetTenantFactory = Callable[..., GetTenant]


class SignUpRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    business_type: str


class ProfileRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    tenant_id: UUID
    role: str
    is_platform_admin: bool


class TenantSummaryRead(BaseModel):
    id: UUID
    name: str
    slug: str
    status: str
    trial_ends_at: datetime
    created_at: datetime


class SignUpResponse(BaseModel):
    profile: ProfileRead
    tenant: TenantSummaryRead


class MeResponse(BaseModel):
    profile: ProfileRead
    tenant: TenantSummaryRead


def _profile_read(profile: Profile) -> ProfileRead:
    return ProfileRead(
        id=profile.id,
        email=profile.email,
        display_name=profile.display_name,
        tenant_id=profile.tenant_id,
        role=profile.role.value,
        is_platform_admin=profile.is_platform_admin,
    )


def _tenant_read(tenant: Tenant) -> TenantSummaryRead:
    return TenantSummaryRead(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        status=tenant.status.value,
        trial_ends_at=tenant.trial_ends_at,
        created_at=tenant.created_at,
    )


def build_me_router(
    sign_up_factory: SignUpFactory,
    get_tenant_factory: GetTenantFactory,
) -> APIRouter:
    router = APIRouter(tags=["me"])

    @router.post("/me/sign-up", response_model=SignUpResponse)
    def sign_up(
        payload: SignUpRequest,
        identity: Annotated[VerifiedToken, Depends(current_identity)],
        use_case: Annotated[SignUp, Depends(sign_up_factory)],
        response: Response,
    ) -> SignUpResponse:
        try:
            result = use_case.execute(
                user_id=identity.user_id,
                email=identity.email,
                business_name=payload.business_name,
                business_type=payload.business_type,
            )
        except DuplicateTenantSlugError as error:
            raise ApiError(409, "tenant_slug_taken") from error
        except InvalidBusinessTypeError as error:
            raise ApiError(422, "business_type_invalid") from error
        except InvalidTenantNameError as error:
            raise ApiError(422, "tenant_name_invalid") from error
        except InvalidTenantSlugError as error:
            raise ApiError(422, "tenant_slug_invalid") from error

        response.status_code = 201 if result.created else 200
        return SignUpResponse(
            profile=_profile_read(result.profile),
            tenant=_tenant_read(result.tenant),
        )

    @router.get("/me", response_model=MeResponse)
    def me(
        profile: Annotated[Profile, Depends(current_profile)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> MeResponse:
        try:
            tenant = get_tenant.execute(profile.tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

        return MeResponse(
            profile=_profile_read(profile),
            tenant=_tenant_read(tenant),
        )

    @router.get("/tenant", response_model=TenantSummaryRead)
    def tenant(
        profile: Annotated[Profile, Depends(current_profile)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> TenantSummaryRead:
        try:
            return _tenant_read(get_tenant.execute(profile.tenant_id))
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

    return router
