"""Cuentas Claras's auth dependencies: the signed-in user's Cuentas Claras profile (an
inmo24x7 profile of the same person never gets in)."""

from followup_core.identity.domain.profile import Role
from followup_platform.auth import build_auth

from .container import get_token_verifier
from .database import get_session
from .product import PRODUCT

AUTH = build_auth(PRODUCT, get_session, get_token_verifier)

current_profile = AUTH.current_profile
require_platform_admin = AUTH.require_platform_admin
# Writes (clients, invoices, imports, payments) are for owners and managers.
require_editor = AUTH.require_role(Role.OWNER, Role.MANAGER)
