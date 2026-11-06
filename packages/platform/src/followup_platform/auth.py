"""Auth dependencies for a product API: the bearer token, the account (a temporary password
must be changed before anything else), the signed-in user's profile in this product (one
person has one profile per product), roles and platform admins.

Each product builds them once with its own session and token-verifier dependencies, so tests
can still override those two by identity (app.dependency_overrides)."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from followup_core.identity.domain.errors import InvalidTokenError
from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.token_verifier import TokenVerifier, VerifiedToken
from followup_core.identity.infrastructure.models import AccountModel
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.infrastructure import log_context
from followup_core.tenancy.domain.product import Product
from followup_core.tenancy.domain.tenant import TenantStatus
from followup_core.tenancy.infrastructure.models import TenantModel
from sqlalchemy.orm import Session

from .http_errors import ApiError

BearerDep = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(HTTPBearer(auto_error=False)),
]


@dataclass(frozen=True, slots=True)
class Auth:
    """FastAPI dependencies; use them as `Depends(auth.current_profile)`."""

    product: Product
    current_identity: Callable[..., VerifiedToken]
    current_account: Callable[..., VerifiedToken]
    current_profile_any_status: Callable[..., Profile]
    current_profile: Callable[..., Profile]
    require_platform_admin: Callable[..., Profile]
    require_role: Callable[..., Callable[..., Profile]]


def build_auth(
    product: Product,
    get_session: Callable[..., Iterator[Session]],
    get_token_verifier: Callable[[], TokenVerifier],
) -> Auth:
    def current_identity(
        credentials: BearerDep,
        verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    ) -> VerifiedToken:
        if credentials is None:
            raise ApiError(401, "unauthorized")
        try:
            return verifier.verify(credentials.credentials)
        except InvalidTokenError as error:
            raise ApiError(401, "unauthorized") from error

    def current_account(
        session: Annotated[Session, Depends(get_session)],
        identity: Annotated[VerifiedToken, Depends(current_identity)],
    ) -> VerifiedToken:
        """403 password_change_required while the account still has its temporary password:
        only /account (to change it) works until then."""
        account = session.get(AccountModel, identity.user_id)
        if account is not None and account.must_change_password:
            raise ApiError(403, "password_change_required")
        return identity

    def current_profile_any_status(
        session: Annotated[Session, Depends(get_session)],
        identity: Annotated[VerifiedToken, Depends(current_account)],
    ) -> Profile:
        """The signed-in user's profile in this product, even when its business is
        suspended (only /me uses it, so the panel can show the suspended screen)."""
        profile = SqlAlchemyProfileRepository(session, product).get_for_user(identity.user_id)
        if profile is None:
            raise ApiError(404, "profile_not_found")
        if not profile.is_platform_admin:
            # Logs and error reports of this request name the business (an admin's own
            # tenant says nothing about which business they are looking at).
            log_context.bind(tenant_id=profile.tenant_id)
        return profile

    def current_profile(
        session: Annotated[Session, Depends(get_session)],
        profile: Annotated[Profile, Depends(current_profile_any_status)],
    ) -> Profile:
        """Every tenant endpoint goes through here: a suspended business gets 403
        tenant_suspended. Platform admins keep working (the backoffice must reach it)."""
        if not profile.is_platform_admin:
            status = session.get(TenantModel, profile.tenant_id)
            if status is not None and status.status == TenantStatus.SUSPENDED.value:
                raise ApiError(403, "tenant_suspended")
        return profile

    def require_role(*roles: Role) -> Callable[..., Profile]:
        def dependency(profile: Annotated[Profile, Depends(current_profile)]) -> Profile:
            if profile.role not in roles:
                raise ApiError(403, "forbidden")
            return profile

        return dependency

    def require_platform_admin(
        profile: Annotated[Profile, Depends(current_profile)],
    ) -> Profile:
        if not profile.is_platform_admin:
            raise ApiError(403, "admin_required")
        return profile

    return Auth(
        product=product,
        current_identity=current_identity,
        current_account=current_account,
        current_profile_any_status=current_profile_any_status,
        current_profile=current_profile,
        require_platform_admin=require_platform_admin,
        require_role=require_role,
    )
