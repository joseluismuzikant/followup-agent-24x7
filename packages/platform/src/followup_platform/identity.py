"""Who is calling and where passwords live, for AUTH_MODE: the token verifier and the
account directory (Supabase Auth's admin API, or a local table in dev mode)."""

import logging

from followup_core.identity.domain.account import AccountDirectory
from followup_core.identity.domain.token_verifier import TokenVerifier
from followup_core.identity.infrastructure.dev_verifier import DevTokenVerifier
from followup_core.identity.infrastructure.directories import (
    DevAccountDirectory,
    SupabaseAccountDirectory,
)
from followup_core.identity.infrastructure.supabase_verifier import SupabaseJwtVerifier
from sqlalchemy.orm import Session

from .settings import Settings

logger = logging.getLogger("followup.identity")


def _issuer(supabase_url: str) -> str | None:
    return f"{supabase_url.rstrip('/')}/auth/v1" if supabase_url else None


def build_token_verifier(settings: Settings) -> TokenVerifier:
    if settings.auth_mode == "dev":
        logger.warning(
            "dev_auth_active",
            extra={"detail": "Only `dev:<email>` tokens are accepted. Development only."},
        )
        return DevTokenVerifier()
    return SupabaseJwtVerifier(
        secret=settings.supabase_jwt_secret or None,
        jwks_url=settings.supabase_jwks_url or None,
        issuer=_issuer(settings.supabase_url),
    )


def build_account_directory(settings: Settings, session: Session) -> AccountDirectory:
    if settings.auth_mode == "dev":
        return DevAccountDirectory(session)
    return SupabaseAccountDirectory(
        settings.supabase_server_url or settings.supabase_url,
        settings.supabase_service_role_key,
    )
