import logging
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from followup_core.identity.domain.token_verifier import TokenVerifier, VerifiedToken
from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
from followup_core.identity.infrastructure.supabase_verifier import (
    FakeTokenVerifier,
    SupabaseJwtVerifier,
)
from followup_core.tenancy.application.create_tenant import CreateTenant
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.application.list_tenants import ListTenants
from followup_core.tenancy.application.sign_up import SignUp
from followup_core.tenancy.infrastructure.repository import SqlAlchemyTenantRepository
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_session

logger = logging.getLogger("inmo24x7.container")

SessionDep = Annotated[Session, Depends(get_session)]


def _issuer(supabase_url: str) -> str | None:
    return f"{supabase_url.rstrip('/')}/auth/v1" if supabase_url else None


@lru_cache
def get_token_verifier() -> TokenVerifier:
    settings = get_settings()
    if settings.supabase_jwt_secret or settings.supabase_jwks_url:
        return SupabaseJwtVerifier(
            secret=settings.supabase_jwt_secret or None,
            jwks_url=settings.supabase_jwks_url or None,
            issuer=_issuer(settings.supabase_url),
        )
    logger.warning(
        "fake_token_verifier_active",
        extra={"detail": "Any bearer token is accepted. Development only."},
    )
    return FakeTokenVerifier(
        default=VerifiedToken(
            user_id=UUID("00000000-0000-0000-0000-000000000001"),
            email="dev@example.com",
        )
    )


def create_tenant_use_case(session: SessionDep) -> CreateTenant:
    return CreateTenant(SqlAlchemyTenantRepository(session))


def list_tenants_use_case(session: SessionDep) -> ListTenants:
    return ListTenants(SqlAlchemyTenantRepository(session))


def get_tenant_use_case(session: SessionDep) -> GetTenant:
    return GetTenant(SqlAlchemyTenantRepository(session))


def sign_up_use_case(session: SessionDep) -> SignUp:
    return SignUp(
        SqlAlchemyTenantRepository(session),
        SqlAlchemyProfileRepository(session),
    )
