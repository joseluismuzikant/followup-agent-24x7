"""Moved to followup_platform.routers.whatsapp (shared with Cuentas Claras); mounted here
with inmo24x7's auth and its Meta error copy."""

from collections.abc import Callable

from fastapi import APIRouter
from followup_core.messaging.application.connections import ManageConnection, SaveConnection
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_platform.routers.whatsapp import (
    AuditFactory,
    ReconnectFactory,
    SignupFactory,
    SignupStateFactory,
    WhatsAppConnectionRead,
    WhatsAppStatusRead,
    connection_read,
    status_read,
)
from followup_platform.routers.whatsapp import build_whatsapp_router as _build

from .auth import AUTH
from .whatsapp_errors import COPY

__all__ = [
    "WhatsAppConnectionRead",
    "WhatsAppStatusRead",
    "build_whatsapp_router",
    "connection_read",
    "status_read",
]


def build_whatsapp_router(
    save_factory: Callable[..., SaveConnection],
    manage_factory: Callable[..., ManageConnection],
    get_tenant_factory: Callable[..., GetTenant],
    signup_factory: SignupFactory,
    signup_state_factory: SignupStateFactory,
    audit_factory: AuditFactory,
    reconnect_factory: ReconnectFactory,
) -> APIRouter:
    return _build(
        AUTH,
        save_factory,
        manage_factory,
        get_tenant_factory,
        signup_factory,
        signup_state_factory,
        audit_factory,
        reconnect_factory,
        COPY,
    )
