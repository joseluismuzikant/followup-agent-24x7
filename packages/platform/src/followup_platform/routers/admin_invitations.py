"""Backoffice actions on a business whose owner has not come in yet: resend the invitation
email, or a new temporary password (shown once). Both product APIs mount it."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from followup_core.identity.application.accounts import (
    InviteOwner,
    ResendInvitation,
    ResetTemporaryPassword,
)
from followup_core.identity.domain.errors import (
    AccountConflictError,
    AccountNotFoundError,
    OwnerAlreadyJoinedError,
)
from followup_core.identity.domain.profile import Profile
from followup_core.identity.infrastructure.directories import AccountDirectoryError
from pydantic import BaseModel

from ..http_errors import ApiError


class InvitationSentRead(BaseModel):
    sent: bool


class TemporaryPasswordRead(BaseModel):
    # Shown once in the backoffice; never stored in clear nor emailed.
    temporary_password: str


def invite_new_owner(use_case: InviteOwner, admin_id: UUID, tenant_id: UUID) -> str | None:
    """After "Dar de alta": the owner's account and the invitation email. The temporary
    password, or None when the person already had an account (the other product)."""
    try:
        return use_case.execute(admin_id, tenant_id).temporary_password
    except AccountConflictError as error:
        raise ApiError(409, "account_conflict") from error
    except AccountDirectoryError as error:
        raise ApiError(503, "auth_provider_unavailable") from error


def build_admin_invitations_router(
    require_platform_admin: Callable[..., Profile],
    resend_factory: Callable[..., ResendInvitation],
    reset_factory: Callable[..., ResetTemporaryPassword],
) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["backoffice"])

    @router.post(
        "/tenants/{tenant_id}/invitation",
        response_model=InvitationSentRead,
        responses={404: {}, 409: {}},
    )
    def resend(
        tenant_id: UUID,
        admin: Annotated[Profile, Depends(require_platform_admin)],
        use_case: Annotated[ResendInvitation, Depends(resend_factory)],
    ) -> InvitationSentRead:
        try:
            use_case.execute(admin.id, tenant_id)
        except AccountNotFoundError as error:
            raise ApiError(404, "invitation_not_found") from error
        except OwnerAlreadyJoinedError as error:
            raise ApiError(409, "owner_already_joined") from error
        return InvitationSentRead(sent=True)

    @router.post(
        "/tenants/{tenant_id}/temporary-password",
        response_model=TemporaryPasswordRead,
        responses={404: {}, 409: {}, 503: {}},
    )
    def reset(
        tenant_id: UUID,
        admin: Annotated[Profile, Depends(require_platform_admin)],
        use_case: Annotated[ResetTemporaryPassword, Depends(reset_factory)],
    ) -> TemporaryPasswordRead:
        try:
            password = use_case.execute(admin.id, tenant_id)
        except AccountNotFoundError as error:
            raise ApiError(404, "invitation_not_found") from error
        except OwnerAlreadyJoinedError as error:
            raise ApiError(409, "owner_already_joined") from error
        except AccountDirectoryError as error:
            raise ApiError(503, "auth_provider_unavailable") from error
        return TemporaryPasswordRead(temporary_password=password)

    return router
