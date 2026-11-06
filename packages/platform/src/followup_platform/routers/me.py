"""/me and sign-up: the signed-in user's profile and business in this product. Sign-up only
joins a business an admin created for this email (invitation-only)."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from followup_core.identity.domain.profile import Profile
from followup_core.identity.domain.token_verifier import VerifiedToken
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.domain.errors import NotInvitedError, TenantNotFoundError
from followup_core.tenancy.domain.tenant import Tenant
from pydantic import BaseModel

from ..auth import Auth
from ..http_errors import ApiError

SignUpFactory = Callable[..., SignUp]
GetTenantFactory = Callable[..., GetTenant]


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
    plan: str
    trial_ends_at: datetime
    created_at: datetime


class SignUpResponse(BaseModel):
    profile: ProfileRead
    tenant: TenantSummaryRead


class MeResponse(BaseModel):
    profile: ProfileRead
    tenant: TenantSummaryRead
    # Shown on the suspended-account screen.
    support_email: str


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
        plan=tenant.plan.value,
        trial_ends_at=tenant.trial_ends_at,
        created_at=tenant.created_at,
    )


def build_me_router(
    auth: Auth,
    sign_up_factory: SignUpFactory,
    get_tenant_factory: GetTenantFactory,
    support_email: str,
) -> APIRouter:
    router = APIRouter(tags=["me"])

    @router.post("/me/sign-up", response_model=SignUpResponse, responses={403: {}})
    def sign_up(
        identity: Annotated[VerifiedToken, Depends(auth.current_account)],
        use_case: Annotated[SignUp, Depends(sign_up_factory)],
        response: Response,
    ) -> SignUpResponse:
        """Joins the business an admin created for the signed-in email (403 not_invited
        otherwise). Idempotent: an existing profile is returned with 200."""
        try:
            result = use_case.execute(user_id=identity.user_id, email=identity.email)
        except NotInvitedError as error:
            raise ApiError(403, "not_invited") from error

        response.status_code = 201 if result.created else 200
        return SignUpResponse(
            profile=_profile_read(result.profile),
            tenant=_tenant_read(result.tenant),
        )

    @router.get("/me", response_model=MeResponse)
    def me(
        profile: Annotated[Profile, Depends(auth.current_profile_any_status)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> MeResponse:
        try:
            tenant = get_tenant.execute(profile.tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

        return MeResponse(
            profile=_profile_read(profile),
            tenant=_tenant_read(tenant),
            support_email=support_email,
        )

    @router.get("/tenant", response_model=TenantSummaryRead)
    def tenant(
        profile: Annotated[Profile, Depends(auth.current_profile)],
        get_tenant: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> TenantSummaryRead:
        try:
            return _tenant_read(get_tenant.execute(profile.tenant_id))
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

    return router
