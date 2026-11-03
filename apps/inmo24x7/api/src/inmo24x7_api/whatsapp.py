"""WhatsApp connection: manual setup for platform admins (backoffice; Day 7 adds Embedded
Signup) and a read-only status for the panel. The access token is never returned."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from followup_core.identity.domain.profile import Profile
from followup_core.messaging.application.connections import (
    ConnectionDraft,
    ConnectionInvalidError,
    ConnectionNotFoundError,
    ManageConnection,
    PhoneNumberTakenError,
    SaveConnection,
    WhatsAppApiError,
)
from followup_core.messaging.domain.connection import SenderKind, WhatsAppConnection
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.domain.errors import TenantNotFoundError
from pydantic import BaseModel, Field

from .auth import current_profile, require_platform_admin
from .http_errors import ApiError, error_response

AdminDep = Annotated[Profile, Depends(require_platform_admin)]
StatusName = Literal["connected", "disconnected", "error", "not_connected"]


class WhatsAppStatusRead(BaseModel):
    """What the panel shows (S5 badge, S4 card)."""

    status: StatusName
    display_phone_number: str | None = None
    verified_name: str | None = None
    last_inbound_at: datetime | None = None
    connected_at: datetime | None = None


class WhatsAppConnectionRead(WhatsAppStatusRead):
    """What admins see. Never the token."""

    phone_number_id: str | None = None
    waba_id: str | None = None
    sender: Literal["cloud", "log"] | None = None
    template_name: str | None = None
    template_language: str | None = None
    # The approved template that confirms a visit outside the 24-hour window.
    visit_template_name: str | None = None
    visit_template_language: str | None = None
    last_error_code: str | None = None
    updated_at: datetime | None = None
    has_access_token: bool = False


class WhatsAppConnectionWrite(BaseModel):
    phone_number_id: str = Field(min_length=1, max_length=64)
    waba_id: str = Field(min_length=1, max_length=64)
    display_phone_number: str | None = Field(default=None, max_length=40)
    # Empty or missing keeps the stored token.
    access_token: str | None = Field(default=None, max_length=4096)
    sender: Literal["cloud", "log"] | None = None
    # Missing keeps the stored template; "" removes it.
    visit_template_name: str | None = Field(default=None, max_length=100)
    visit_template_language: str | None = Field(default=None, max_length=20)


class TestMessageWrite(BaseModel):
    to: str = Field(min_length=6, max_length=32)


class TestMessageRead(BaseModel):
    wamid: str


def status_read(connection: WhatsAppConnection | None) -> WhatsAppStatusRead:
    if connection is None:
        return WhatsAppStatusRead(status="not_connected")
    return WhatsAppStatusRead(
        status=connection.status.value,
        display_phone_number=connection.display_phone_number,
        verified_name=connection.verified_name,
        last_inbound_at=connection.last_inbound_at,
        connected_at=connection.connected_at,
    )


def connection_read(connection: WhatsAppConnection | None) -> WhatsAppConnectionRead:
    base = status_read(connection).model_dump()
    if connection is None:
        return WhatsAppConnectionRead(**base)
    return WhatsAppConnectionRead(
        **base,
        phone_number_id=connection.phone_number_id,
        waba_id=connection.waba_id,
        sender=connection.sender.value,
        template_name=connection.template_name,
        template_language=connection.template_language,
        visit_template_name=connection.visit_template_name,
        visit_template_language=connection.visit_template_language,
        last_error_code=connection.last_error_code,
        updated_at=connection.updated_at,
        has_access_token=bool(connection.access_token_encrypted),
    )


def meta_error(error: WhatsAppApiError) -> JSONResponse:
    """Returned, not raised: raising would roll back the connection's new error state
    (status "error" and Meta's code), which admins need to see."""
    return error_response(502, "whatsapp_api_error", {"meta_code": error.meta_code})


def build_whatsapp_router(
    save_factory: Callable[..., SaveConnection],
    manage_factory: Callable[..., ManageConnection],
    get_tenant_factory: Callable[..., GetTenant],
) -> APIRouter:
    router = APIRouter(tags=["whatsapp"])
    prefix = "/admin/tenants/{tenant_id}/whatsapp"

    def require_tenant(tenant_id: UUID, tenants: GetTenant) -> None:
        try:
            tenants.execute(tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

    def run(action: Callable[[], WhatsAppConnection]) -> WhatsAppConnectionRead | JSONResponse:
        try:
            return connection_read(action())
        except ConnectionNotFoundError as error:
            raise ApiError(404, "whatsapp_not_connected") from error
        except WhatsAppApiError as error:
            return meta_error(error)

    @router.get("/whatsapp", response_model=WhatsAppStatusRead)
    def panel_status(
        profile: Annotated[Profile, Depends(current_profile)],
        manage: Annotated[ManageConnection, Depends(manage_factory)],
    ) -> WhatsAppStatusRead:
        return status_read(manage.get(profile.tenant_id))

    @router.get(prefix, response_model=WhatsAppConnectionRead)
    def admin_get(
        tenant_id: UUID,
        _admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead:
        require_tenant(tenant_id, tenants)
        return connection_read(manage.get(tenant_id))

    @router.put(prefix, response_model=WhatsAppConnectionRead)
    def admin_save(
        tenant_id: UUID,
        payload: WhatsAppConnectionWrite,
        _admin: AdminDep,
        save: Annotated[SaveConnection, Depends(save_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead:
        require_tenant(tenant_id, tenants)
        draft = ConnectionDraft(
            phone_number_id=payload.phone_number_id,
            waba_id=payload.waba_id,
            display_phone_number=(payload.display_phone_number or "").strip() or None,
            access_token=(payload.access_token or "").strip() or None,
            sender=SenderKind(payload.sender) if payload.sender else None,
            visit_template_name=payload.visit_template_name,
            visit_template_language=(payload.visit_template_language or "").strip() or None,
        )
        try:
            return connection_read(save.execute(tenant_id, draft))
        except ConnectionInvalidError as error:
            raise ApiError(422, "whatsapp_connection_invalid") from error
        except PhoneNumberTakenError as error:
            raise ApiError(409, "whatsapp_phone_number_taken") from error

    @router.post(f"{prefix}/test", response_model=WhatsAppConnectionRead)
    def admin_test(
        tenant_id: UUID,
        _admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead | JSONResponse:
        require_tenant(tenant_id, tenants)
        return run(lambda: manage.test(tenant_id))

    @router.post(f"{prefix}/subscribe", response_model=WhatsAppConnectionRead)
    def admin_subscribe(
        tenant_id: UUID,
        _admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead | JSONResponse:
        require_tenant(tenant_id, tenants)
        return run(lambda: manage.subscribe(tenant_id))

    @router.post(f"{prefix}/test-message", response_model=TestMessageRead)
    def admin_test_message(
        tenant_id: UUID,
        payload: TestMessageWrite,
        _admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> TestMessageRead | JSONResponse:
        require_tenant(tenant_id, tenants)
        try:
            return TestMessageRead(wamid=manage.send_test_message(tenant_id, payload.to))
        except ConnectionNotFoundError as error:
            raise ApiError(404, "whatsapp_not_connected") from error
        except ConnectionInvalidError as error:
            raise ApiError(422, "whatsapp_connection_invalid") from error
        except WhatsAppApiError as error:
            return meta_error(error)

    @router.post(f"{prefix}/disconnect", response_model=WhatsAppConnectionRead)
    def admin_disconnect(
        tenant_id: UUID,
        _admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead | JSONResponse:
        require_tenant(tenant_id, tenants)
        return run(lambda: manage.disconnect(tenant_id))

    return router
