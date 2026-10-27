from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from followup_core.identity.domain.errors import InvalidTokenError
from followup_core.identity.domain.profile import Profile, Role
from followup_core.identity.domain.token_verifier import TokenVerifier, VerifiedToken
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from sqlalchemy.orm import Session

from .container import get_token_verifier
from .database import get_session
from .http_errors import ApiError

SessionDep = Annotated[Session, Depends(get_session)]
VerifierDep = Annotated[TokenVerifier, Depends(get_token_verifier)]
BearerDep = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(HTTPBearer(auto_error=False)),
]


def current_identity(credentials: BearerDep, verifier: VerifierDep) -> VerifiedToken:
    if credentials is None:
        raise ApiError(401, "unauthorized")
    try:
        return verifier.verify(credentials.credentials)
    except InvalidTokenError as error:
        raise ApiError(401, "unauthorized") from error


def current_profile(
    session: SessionDep,
    identity: Annotated[VerifiedToken, Depends(current_identity)],
) -> Profile:
    profile = SqlAlchemyProfileRepository(session).get_by_id(identity.user_id)
    if profile is None:
        raise ApiError(404, "profile_not_found")
    return profile


def require_role(*roles: Role) -> Callable[[Profile], Profile]:
    def dependency(
        profile: Annotated[Profile, Depends(current_profile)],
    ) -> Profile:
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
