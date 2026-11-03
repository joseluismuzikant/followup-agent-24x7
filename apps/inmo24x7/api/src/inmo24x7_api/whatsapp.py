"""WhatsApp connection: Embedded Signup and the S4 status for the panel, and the manual
setup, retry and reconnect link for platform admins (the fallback while a customer cannot
use Embedded Signup). The access token is never returned."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from followup_core.identity.domain.profile import Profile, Role
from followup_core.messaging.application.connections import (
    ConnectionDraft,
    ConnectionInvalidError,
    ConnectionNotFoundError,
    ManageConnection,
    PhoneNumberTakenError,
    SaveConnection,
    WhatsAppApiError,
)
from followup_core.messaging.application.signup import (
    CompleteEmbeddedSignup,
    SignupFailedError,
    SignupRequest,
    SignupRestartError,
)
from followup_core.messaging.domain.connection import SenderKind, WhatsAppConnection
from followup_core.messaging.domain.signup import Signup
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog
from followup_core.tenancy.domain.errors import TenantNotFoundError
from pydantic import BaseModel, Field

from .auth import current_profile, require_platform_admin, require_role
from .http_errors import ApiError, error_response
from .whatsapp_errors import TranslatedError, translate

AdminDep = Annotated[Profile, Depends(require_platform_admin)]
StatusName = Literal["connected", "disconnected", "error", "not_connected"]
Verification = Literal["verified", "pending", "failed", "unknown"]
can_connect = require_role(Role.OWNER, Role.MANAGER)


class WhatsAppErrorRead(BaseModel):
    """A Meta error in plain Spanish (title, what happened, what to do)."""

    code: str
    title: str
    message: str
    action: str


class WhatsAppAdminErrorRead(WhatsAppErrorRead):
    meta_code: str
    admin_detail: str


class WhatsAppStatusRead(BaseModel):
    """What the panel shows (S5 badge, S4 card, the error banner)."""

    status: StatusName
    display_phone_number: str | None = None
    verified_name: str | None = None
    last_inbound_at: datetime | None = None
    connected_at: datetime | None = None
    quality_rating: str | None = None
    business_verification: Verification | None = None
    # Since when messages stop going out (the connection is in error).
    failing_since: datetime | None = None
    error: WhatsAppErrorRead | None = None
    # Embedded Signup progress when it stopped halfway ("Reintentar configuración").
    signup_step: str | None = None
    signup_error: WhatsAppErrorRead | None = None


class WhatsAppConnectionRead(WhatsAppStatusRead):
    """What admins see. Never the token."""

    phone_number_id: str | None = None
    waba_id: str | None = None
    business_id: str | None = None
    sender: Literal["cloud", "log"] | None = None
    template_name: str | None = None
    template_language: str | None = None
    # The approved template that confirms a visit outside the 24-hour window.
    visit_template_name: str | None = None
    visit_template_language: str | None = None
    last_error_code: str | None = None
    admin_error: WhatsAppAdminErrorRead | None = None
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


class EmbeddedSignupWrite(BaseModel):
    """What Meta's popup gave the panel: the 30-second code and the ids (FINISH event)."""

    code: str = Field(min_length=1, max_length=2048)
    waba_id: str = Field(min_length=1, max_length=64)
    phone_number_id: str = Field(min_length=1, max_length=64)
    business_id: str | None = Field(default=None, max_length=64)


class SignupAbandonedWrite(BaseModel):
    """CANCEL, ERROR or FINISH_ONLY_WABA from Meta's popup (no personal data)."""

    event: Literal["CANCEL", "ERROR", "FINISH_ONLY_WABA", "FINISH_GRANT_ONLY_API_ACCESS"]
    current_step: str | None = Field(default=None, max_length=60)
    error_code: str | None = Field(default=None, max_length=40)


class SignupAbandonedRead(BaseModel):
    """Meta's popup error code in plain Spanish (null without a code)."""

    error: WhatsAppErrorRead | None


class TestMessageWrite(BaseModel):
    to: str = Field(min_length=6, max_length=32)


class TestMessageRead(BaseModel):
    wamid: str


class ReconnectLinkRead(BaseModel):
    recipients: int


def _error(translated: TranslatedError) -> WhatsAppErrorRead:
    return WhatsAppErrorRead(
        code=translated.code,
        title=translated.title,
        message=translated.message,
        action=translated.action,
    )


def _admin_error(translated: TranslatedError) -> WhatsAppAdminErrorRead:
    return WhatsAppAdminErrorRead(
        **_error(translated).model_dump(),
        meta_code=translated.meta_code,
        admin_detail=translated.admin_detail,
    )


def _unfinished(signup: Signup | None) -> Signup | None:
    return signup if signup is not None and signup.step.value != "connected" else None


def status_read(
    connection: WhatsAppConnection | None, signup: Signup | None = None
) -> WhatsAppStatusRead:
    pending = _unfinished(signup)
    signup_fields = {
        "signup_step": pending.step.value if pending else None,
        "signup_error": (
            _error(translate(pending.last_error_code))
            if pending and pending.last_error_code
            else None
        ),
    }
    if connection is None:
        return WhatsAppStatusRead(status="not_connected", **signup_fields)
    failing = connection.is_failing
    return WhatsAppStatusRead(
        status=connection.status.value,
        display_phone_number=connection.display_phone_number,
        verified_name=connection.verified_name,
        last_inbound_at=connection.last_inbound_at,
        connected_at=connection.connected_at,
        quality_rating=connection.quality_rating,
        business_verification=connection.business_verification.value,
        failing_since=connection.failing_since if failing else None,
        error=_error(translate(connection.last_error_code)) if failing else None,
        **signup_fields,
    )


def connection_read(
    connection: WhatsAppConnection | None, signup: Signup | None = None
) -> WhatsAppConnectionRead:
    base = status_read(connection, signup).model_dump()
    if connection is None:
        return WhatsAppConnectionRead(**base)
    return WhatsAppConnectionRead(
        **base,
        phone_number_id=connection.phone_number_id,
        waba_id=connection.waba_id,
        business_id=connection.business_id,
        sender=connection.sender.value,
        template_name=connection.template_name,
        template_language=connection.template_language,
        visit_template_name=connection.visit_template_name,
        visit_template_language=connection.visit_template_language,
        last_error_code=connection.last_error_code,
        admin_error=(
            _admin_error(translate(connection.last_error_code))
            if connection.last_error_code
            else None
        ),
        updated_at=connection.updated_at,
        has_access_token=bool(connection.access_token_encrypted),
    )


def meta_error(error: WhatsAppApiError) -> JSONResponse:
    """Returned, not raised: raising would roll back the connection's new error state
    (status "error" and Meta's code), which admins need to see."""
    return error_response(502, "whatsapp_api_error", {"meta_code": error.meta_code})


def signup_failed(error: SignupFailedError) -> JSONResponse:
    """Returned, not raised, so the progress up to the failed step is kept."""
    return error_response(
        502,
        "whatsapp_signup_failed",
        {
            "step": error.step.value,
            "meta_code": error.meta_code,
            "error": _error(translate(error.meta_code)).model_dump(),
        },
    )


SignupFactory = Callable[..., CompleteEmbeddedSignup]
SignupStateFactory = Callable[..., Callable[[UUID], Signup | None]]
AuditFactory = Callable[..., AuditLog]
ReconnectFactory = Callable[..., Callable[[UUID, UUID], int]]


def build_whatsapp_router(
    save_factory: Callable[..., SaveConnection],
    manage_factory: Callable[..., ManageConnection],
    get_tenant_factory: Callable[..., GetTenant],
    signup_factory: SignupFactory,
    signup_state_factory: SignupStateFactory,
    audit_factory: AuditFactory,
    reconnect_factory: ReconnectFactory,
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

    def run_signup(
        action: Callable[[], WhatsAppConnection],
    ) -> WhatsAppConnection | JSONResponse:
        try:
            return action()
        except ConnectionInvalidError as error:
            raise ApiError(422, "whatsapp_connection_invalid") from error
        except PhoneNumberTakenError as error:
            raise ApiError(409, "whatsapp_phone_number_taken") from error
        except SignupRestartError as error:
            raise ApiError(409, "whatsapp_signup_restart") from error
        except SignupFailedError as error:
            return signup_failed(error)

    @router.get("/whatsapp", response_model=WhatsAppStatusRead)
    def panel_status(
        profile: Annotated[Profile, Depends(current_profile)],
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        signup_state: Annotated[Callable[[UUID], Signup | None], Depends(signup_state_factory)],
    ) -> WhatsAppStatusRead:
        return status_read(manage.get(profile.tenant_id), signup_state(profile.tenant_id))

    @router.post(
        "/whatsapp/embedded-signup",
        response_model=WhatsAppStatusRead,
        responses={409: {}, 422: {}, 502: {}},
    )
    def embedded_signup(
        payload: EmbeddedSignupWrite,
        profile: Annotated[Profile, Depends(can_connect)],
        signup: Annotated[CompleteEmbeddedSignup, Depends(signup_factory)],
    ) -> WhatsAppStatusRead | JSONResponse:
        request = SignupRequest(
            waba_id=payload.waba_id,
            phone_number_id=payload.phone_number_id,
            business_id=payload.business_id,
            code=payload.code,
        )
        result = run_signup(lambda: signup.execute(profile.tenant_id, request, profile.id))
        return result if isinstance(result, JSONResponse) else status_read(result)

    @router.post(
        "/whatsapp/embedded-signup/retry",
        response_model=WhatsAppStatusRead,
        responses={409: {}, 502: {}},
    )
    def retry_signup(
        profile: Annotated[Profile, Depends(can_connect)],
        signup: Annotated[CompleteEmbeddedSignup, Depends(signup_factory)],
        signup_state: Annotated[Callable[[UUID], Signup | None], Depends(signup_state_factory)],
    ) -> WhatsAppStatusRead | JSONResponse:
        result = _retry(profile.tenant_id, profile.id, signup, signup_state, run_signup)
        return result if isinstance(result, JSONResponse) else status_read(result)

    @router.post("/whatsapp/embedded-signup/abandoned", response_model=SignupAbandonedRead)
    def signup_abandoned(
        payload: SignupAbandonedWrite,
        profile: Annotated[Profile, Depends(can_connect)],
        audit: Annotated[AuditLog, Depends(audit_factory)],
    ) -> SignupAbandonedRead:
        audit.record(
            AuditEvent(
                profile.tenant_id,
                datetime.now(UTC),
                ActorKind.USER,
                AuditAction.WHATSAPP_SIGNUP_ABANDONED,
                {
                    "event": payload.event,
                    "step": payload.current_step,
                    "meta_code": payload.error_code,
                },
                actor_profile_id=profile.id,
            )
        )
        return SignupAbandonedRead(
            error=_error(translate(payload.error_code)) if payload.error_code else None
        )

    @router.get(prefix, response_model=WhatsAppConnectionRead)
    def admin_get(
        tenant_id: UUID,
        _admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
        signup_state: Annotated[Callable[[UUID], Signup | None], Depends(signup_state_factory)],
    ) -> WhatsAppConnectionRead:
        require_tenant(tenant_id, tenants)
        return connection_read(manage.get(tenant_id), signup_state(tenant_id))

    @router.put(prefix, response_model=WhatsAppConnectionRead)
    def admin_save(
        tenant_id: UUID,
        payload: WhatsAppConnectionWrite,
        admin: AdminDep,
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
            return connection_read(save.execute(tenant_id, draft, admin.id))
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
        admin: AdminDep,
        manage: Annotated[ManageConnection, Depends(manage_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead | JSONResponse:
        require_tenant(tenant_id, tenants)
        return run(lambda: manage.disconnect(tenant_id, admin.id))

    @router.post(
        f"{prefix}/retry-signup",
        response_model=WhatsAppConnectionRead,
        responses={409: {}, 502: {}},
    )
    def admin_retry_signup(
        tenant_id: UUID,
        _admin: AdminDep,
        signup: Annotated[CompleteEmbeddedSignup, Depends(signup_factory)],
        signup_state: Annotated[Callable[[UUID], Signup | None], Depends(signup_state_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> WhatsAppConnectionRead | JSONResponse:
        require_tenant(tenant_id, tenants)
        result = _retry(tenant_id, None, signup, signup_state, run_signup)
        if isinstance(result, JSONResponse):
            return result
        return connection_read(result, signup_state(tenant_id))

    @router.post(f"{prefix}/reconnect-link", response_model=ReconnectLinkRead, status_code=202)
    def admin_reconnect_link(
        tenant_id: UUID,
        admin: AdminDep,
        reconnect: Annotated[Callable[[UUID, UUID], int], Depends(reconnect_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
    ) -> ReconnectLinkRead:
        require_tenant(tenant_id, tenants)
        recipients = reconnect(tenant_id, admin.id)
        if recipients == 0:
            raise ApiError(409, "tenant_has_no_owner")
        return ReconnectLinkRead(recipients=recipients)

    return router


def _retry(
    tenant_id: UUID,
    profile_id: UUID | None,
    signup: CompleteEmbeddedSignup,
    signup_state: Callable[[UUID], Signup | None],
    run_signup: Callable[[Callable[[], WhatsAppConnection]], WhatsAppConnection | JSONResponse],
) -> WhatsAppConnection | JSONResponse:
    """ "Reintentar configuración": resumes the stored signup (no Meta popup)."""
    stored = signup_state(tenant_id)
    if stored is None:
        raise ApiError(409, "whatsapp_signup_restart")
    request = SignupRequest(stored.waba_id, stored.phone_number_id, stored.business_id)
    return run_signup(lambda: signup.execute(tenant_id, request, profile_id))
