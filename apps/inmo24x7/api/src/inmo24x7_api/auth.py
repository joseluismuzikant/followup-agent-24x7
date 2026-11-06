"""inmo24x7's auth dependencies (built by followup_platform.auth for this product)."""

from followup_platform.auth import BearerDep, build_auth

from .container import get_token_verifier
from .database import get_session
from .product import PRODUCT

AUTH = build_auth(PRODUCT, get_session, get_token_verifier)

current_identity = AUTH.current_identity
current_profile_any_status = AUTH.current_profile_any_status
current_profile = AUTH.current_profile
require_role = AUTH.require_role
require_platform_admin = AUTH.require_platform_admin

__all__ = [
    "AUTH",
    "BearerDep",
    "current_identity",
    "current_profile",
    "current_profile_any_status",
    "require_platform_admin",
    "require_role",
]
