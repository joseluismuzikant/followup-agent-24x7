"""The account, before any profile: the forced password change, the invitation link and the
development sign-in. Both product APIs mount it."""

from collections.abc import Callable, Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from followup_core.identity.application.accounts import (
    AcceptInvitation,
    ChangePassword,
    GetInvitation,
)
from followup_core.identity.domain.account import AccountDirectory
from followup_core.identity.domain.errors import (
    AccountConflictError,
    AccountNotFoundError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationUsedError,
    WeakPasswordError,
)
from followup_core.identity.domain.token_verifier import VerifiedToken
from followup_core.identity.infrastructure.accounts import (
    SqlAlchemyAccountRepository,
    SqlAlchemyInvitationRepository,
)
from followup_core.identity.infrastructure.dev_verifier import DEV_TOKEN_PREFIX
from followup_core.identity.infrastructure.directories import (
    AccountDirectoryError,
    DevAccountDirectory,
)
from followup_core.tenancy.infrastructure.audit_repository import SqlAlchemyAuditLog
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import Auth
from ..http_errors import ApiError
from ..settings import Settings


class AccountRead(BaseModel):
    email: str
    must_change_password: bool


class PasswordChange(BaseModel):
    password: str = Field(max_length=200)


class InvitationRead(BaseModel):
    email: str
    business_name: str
    status: Literal["valid", "expired", "used"]
    needs_password: bool


class InvitationAccept(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    password: str = Field(max_length=200)


class InvitationAccepted(BaseModel):
    email: str


class DevSignIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(max_length=200)


class DevSession(BaseModel):
    access_token: str


def _password_errors(error: Exception) -> ApiError:
    if isinstance(error, WeakPasswordError):
        return ApiError(422, error.code)
    return ApiError(503, "auth_provider_unavailable")


def build_account_router(
    auth: Auth,
    get_session: Callable[..., Iterator[Session]],
    get_settings: Callable[[], Settings],
    get_account_directory: Callable[..., AccountDirectory],
) -> APIRouter:
    router = APIRouter(tags=["account"])

    @router.get("/account", response_model=AccountRead)
    def account(
        session: Annotated[Session, Depends(get_session)],
        identity: Annotated[VerifiedToken, Depends(auth.current_identity)],
    ) -> AccountRead:
        found = SqlAlchemyAccountRepository(session).get(identity.user_id)
        return AccountRead(
            email=identity.email,
            must_change_password=found.must_change_password if found else False,
        )

    @router.post("/account/password", status_code=204, responses={422: {}, 503: {}})
    def change_password(
        payload: PasswordChange,
        session: Annotated[Session, Depends(get_session)],
        directory: Annotated[AccountDirectory, Depends(get_account_directory)],
        identity: Annotated[VerifiedToken, Depends(auth.current_identity)],
    ) -> None:
        use_case = ChangePassword(SqlAlchemyAccountRepository(session), directory)
        try:
            use_case.execute(identity.user_id, identity.email, payload.password)
        except (WeakPasswordError, AccountDirectoryError) as error:
            raise _password_errors(error) from error

    @router.get("/invitations/{token}", response_model=InvitationRead, responses={404: {}})
    def invitation(token: str, session: Annotated[Session, Depends(get_session)]) -> InvitationRead:
        use_case = GetInvitation(
            SqlAlchemyInvitationRepository(session),
            SqlAlchemyAccountRepository(session),
            SqlAlchemyTenantRepository(session, auth.product),
        )
        try:
            view = use_case.execute(token)
        except InvitationNotFoundError as error:
            raise ApiError(404, "invitation_not_found") from error
        return InvitationRead(
            email=view.email,
            business_name=view.business_name,
            status=view.status.value,
            needs_password=view.needs_password,
        )

    @router.post(
        "/invitations/accept",
        response_model=InvitationAccepted,
        responses={404: {}, 409: {}, 410: {}, 422: {}, 503: {}},
    )
    def accept_invitation(
        payload: InvitationAccept,
        session: Annotated[Session, Depends(get_session)],
        directory: Annotated[AccountDirectory, Depends(get_account_directory)],
    ) -> InvitationAccepted:
        invitations = SqlAlchemyInvitationRepository(session)
        found = invitations.get_by_token(payload.token)
        # A link of the other product is not this API's.
        if found is None or found.product != auth.product:
            raise ApiError(404, "invitation_not_found")
        use_case = AcceptInvitation(
            invitations,
            SqlAlchemyAccountRepository(session),
            directory,
            SqlAlchemyAuditLog(session),
        )
        try:
            email = use_case.execute(payload.token, payload.password)
        except (InvitationNotFoundError, AccountNotFoundError) as error:
            raise ApiError(404, "invitation_not_found") from error
        except InvitationUsedError as error:
            raise ApiError(409, "invitation_used") from error
        except InvitationExpiredError as error:
            raise ApiError(410, "invitation_expired") from error
        except (WeakPasswordError, AccountDirectoryError, AccountConflictError) as error:
            raise _password_errors(error) from error
        return InvitationAccepted(email=email)

    @router.post("/auth/dev/sign-in", response_model=DevSession, responses={401: {}, 404: {}})
    def dev_sign_in(
        payload: DevSignIn, session: Annotated[Session, Depends(get_session)]
    ) -> DevSession:
        """AUTH_MODE=dev only: checks the local password and returns a `dev:<email>` token
        (Supabase Auth does this in production)."""
        if get_settings().auth_mode != "dev":
            raise ApiError(404, "not_found")
        email = payload.email.strip().lower()
        if not DevAccountDirectory(session).verify(email, payload.password):
            raise ApiError(401, "invalid_credentials")
        return DevSession(access_token=f"{DEV_TOKEN_PREFIX}{email}")

    return router
