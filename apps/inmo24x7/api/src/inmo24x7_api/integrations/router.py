"""Configuración → Integraciones (owner and manager change them; everyone sees them), the
lead panel's delivery status, and the website button's public configuration."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from followup_core.identity.domain.profile import Profile, Role
from pydantic import BaseModel, Field

from ..auth import current_profile, require_role
from ..http_errors import ApiError
from .application import (
    MAX_KEY_LENGTH,
    MAX_LABEL_LENGTH,
    GetPublicWidget,
    IntegrationsView,
    IntegrationUseCases,
)
from .domain import Integration, IntegrationError, LeadDelivery, SyncReport

WriterDep = Annotated[Profile, Depends(require_role(Role.OWNER, Role.MANAGER))]
ReaderDep = Annotated[Profile, Depends(current_profile)]

# HTTP status per error code.
_STATUS = {
    "tokko_key_invalid": 422,
    "tokko_unavailable": 503,
    "tokko_bad_response": 503,
    "tokko_not_connected": 409,
    "webhook_url_invalid": 422,
    "webhook_not_configured": 409,
    "widget_invalid": 422,
}


def _error(error: IntegrationError) -> ApiError:
    return ApiError(_STATUS.get(error.code, 409), error.code)


class DeliveryRead(BaseModel):
    id: UUID
    provider: Literal["tokko", "webhook"]
    event: str
    status: Literal["pending", "retrying", "delivered", "failed"]
    attempts: int
    status_code: int | None
    error_code: str | None
    lead_id: UUID | None
    created_at: datetime
    delivered_at: datetime | None


class SyncFailureRead(BaseModel):
    external_id: str
    title: str
    reason: str


class SyncReportRead(BaseModel):
    started_at: datetime
    finished_at: datetime
    created: int
    updated: int
    paused: int
    unchanged: int
    failed: list[SyncFailureRead]
    error_code: str | None


class TokkoRead(BaseModel):
    connected: bool
    import_properties: bool
    send_leads: bool
    last_sync_at: datetime | None
    last_sync_status: Literal["queued", "ok", "failed"] | None
    last_error_code: str | None
    last_report: SyncReportRead | None
    deliveries: list[DeliveryRead]


class WebhookRead(BaseModel):
    configured: bool
    enabled: bool
    url: str | None
    has_secret: bool
    last_delivery_at: datetime | None
    last_delivery_status: Literal["pending", "retrying", "delivered", "failed"] | None
    deliveries: list[DeliveryRead]


class WidgetRead(BaseModel):
    public_id: str
    enabled: bool
    color: str
    text_color: str
    position: Literal["right", "left"]
    label: str
    whatsapp_connected: bool


class IntegrationsRead(BaseModel):
    tokko: TokkoRead
    webhook: WebhookRead
    widget: WidgetRead


class TokkoConnect(BaseModel):
    api_key: str = Field(min_length=1, max_length=MAX_KEY_LENGTH)


class TokkoOptions(BaseModel):
    import_properties: bool
    send_leads: bool


class WebhookWrite(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    enabled: bool = True


class WebhookSavedRead(BaseModel):
    webhook: WebhookRead
    # Only when it was just generated: shown once.
    secret: str | None


class WidgetWrite(BaseModel):
    enabled: bool = True
    color: str = Field(max_length=7)
    text_color: str = Field(max_length=7)
    position: Literal["right", "left"] = "right"
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)


class PublicWidgetRead(BaseModel):
    agency_name: str
    phone: str | None
    color: str
    text_color: str
    position: str
    label: str


def delivery_read(item: LeadDelivery) -> DeliveryRead:
    return DeliveryRead(
        id=item.id,
        provider=item.provider.value,  # type: ignore[arg-type]
        event=item.event,
        status=item.status.value,
        attempts=item.attempts,
        status_code=item.status_code,
        error_code=item.error_code,
        lead_id=item.lead_id,
        created_at=item.created_at,
        delivered_at=item.delivered_at,
    )


def _report(report: SyncReport | None) -> SyncReportRead | None:
    if report is None:
        return None
    return SyncReportRead(
        started_at=report.started_at,
        finished_at=report.finished_at,
        created=report.created,
        updated=report.updated,
        paused=report.paused,
        unchanged=report.unchanged,
        failed=[
            SyncFailureRead(external_id=f.external_id, title=f.title, reason=f.reason)
            for f in report.failed
        ],
        error_code=report.error_code,
    )


def _tokko(view: IntegrationsView) -> TokkoRead:
    item = view.tokko
    connected = bool(item and item.enabled and item.credentials)
    return TokkoRead(
        connected=connected,
        import_properties=bool(item.option("import_properties")) if item else True,
        send_leads=bool(item.option("send_leads")) if item else True,
        last_sync_at=item.last_sync_at if item else None,
        last_sync_status=item.last_sync_status.value if item and item.last_sync_status else None,
        last_error_code=item.last_error_code if item else None,
        last_report=_report(view.tokko_report),
        deliveries=[delivery_read(d) for d in view.tokko_deliveries],
    )


def _webhook(item: Integration | None, deliveries: list[LeadDelivery]) -> WebhookRead:
    url = item.options.get("url") if item else None
    return WebhookRead(
        configured=bool(url),
        enabled=bool(item and item.enabled and url),
        url=url,
        has_secret=bool(item and item.credentials),
        last_delivery_at=item.last_delivery_at if item else None,
        last_delivery_status=item.last_delivery_status.value
        if item and item.last_delivery_status
        else None,
        deliveries=[delivery_read(d) for d in deliveries],
    )


def _widget(item: Integration, whatsapp: bool) -> WidgetRead:
    return WidgetRead(
        public_id=item.public_id or "",
        enabled=item.enabled,
        color=str(item.option("color")),
        text_color=str(item.option("text_color")),
        position=item.option("position"),
        label=str(item.option("label")),
        whatsapp_connected=whatsapp,
    )


def build_integrations_router(
    use_cases_factory: Callable[..., IntegrationUseCases],
    public_widget_factory: Callable[..., GetPublicWidget],
) -> APIRouter:
    router = APIRouter(tags=["integrations"])

    def _read(use_cases: IntegrationUseCases, tenant_id: UUID) -> IntegrationsRead:
        view = use_cases.get.execute(tenant_id)
        return IntegrationsRead(
            tokko=_tokko(view),
            webhook=_webhook(view.webhook, list(view.webhook_deliveries)),
            widget=_widget(view.widget, use_cases.whatsapp_number(tenant_id) is not None),
        )

    @router.get("/integrations", response_model=IntegrationsRead)
    def get_integrations(
        profile: ReaderDep, use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)]
    ) -> IntegrationsRead:
        return _read(use_cases, profile.tenant_id)

    @router.put("/integrations/tokko", response_model=IntegrationsRead)
    def connect_tokko(
        payload: TokkoConnect,
        profile: WriterDep,
        use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)],
    ) -> IntegrationsRead:
        try:
            use_cases.connect_tokko.execute(profile.tenant_id, profile.id, payload.api_key)
        except IntegrationError as error:
            raise _error(error) from error
        return _read(use_cases, profile.tenant_id)

    @router.patch("/integrations/tokko", response_model=IntegrationsRead)
    def update_tokko(
        payload: TokkoOptions,
        profile: WriterDep,
        use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)],
    ) -> IntegrationsRead:
        try:
            use_cases.update_tokko.execute(
                profile.tenant_id, profile.id, payload.import_properties, payload.send_leads
            )
        except IntegrationError as error:
            raise _error(error) from error
        return _read(use_cases, profile.tenant_id)

    @router.delete("/integrations/tokko", response_model=IntegrationsRead)
    def disconnect_tokko(
        profile: WriterDep, use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)]
    ) -> IntegrationsRead:
        use_cases.disconnect_tokko.execute(profile.tenant_id, profile.id)
        return _read(use_cases, profile.tenant_id)

    @router.post("/integrations/tokko/sync", response_model=IntegrationsRead, status_code=202)
    def sync_tokko(
        profile: WriterDep, use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)]
    ) -> IntegrationsRead:
        try:
            use_cases.sync_tokko.execute(profile.tenant_id)
        except IntegrationError as error:
            raise _error(error) from error
        return _read(use_cases, profile.tenant_id)

    @router.put("/integrations/webhook", response_model=WebhookSavedRead)
    def configure_webhook(
        payload: WebhookWrite,
        profile: WriterDep,
        use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)],
    ) -> WebhookSavedRead:
        try:
            saved = use_cases.configure_webhook.execute(
                profile.tenant_id, profile.id, payload.url, payload.enabled
            )
        except IntegrationError as error:
            raise _error(error) from error
        view = _read(use_cases, profile.tenant_id)
        return WebhookSavedRead(webhook=view.webhook, secret=saved.secret)

    @router.post("/integrations/webhook/secret", response_model=WebhookSavedRead)
    def rotate_secret(
        profile: WriterDep, use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)]
    ) -> WebhookSavedRead:
        try:
            saved = use_cases.rotate_secret.execute(profile.tenant_id, profile.id)
        except IntegrationError as error:
            raise _error(error) from error
        view = _read(use_cases, profile.tenant_id)
        return WebhookSavedRead(webhook=view.webhook, secret=saved.secret)

    @router.delete("/integrations/webhook", response_model=IntegrationsRead)
    def delete_webhook(
        profile: WriterDep, use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)]
    ) -> IntegrationsRead:
        use_cases.delete_webhook.execute(profile.tenant_id, profile.id)
        return _read(use_cases, profile.tenant_id)

    @router.post("/integrations/webhook/test", response_model=DeliveryRead)
    def test_webhook(
        profile: WriterDep, use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)]
    ) -> DeliveryRead:
        try:
            return delivery_read(use_cases.test_webhook.execute(profile.tenant_id))
        except IntegrationError as error:
            raise _error(error) from error

    @router.put("/integrations/widget", response_model=IntegrationsRead)
    def save_widget(
        payload: WidgetWrite,
        profile: WriterDep,
        use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)],
    ) -> IntegrationsRead:
        try:
            use_cases.save_widget.execute(
                profile.tenant_id,
                profile.id,
                enabled=payload.enabled,
                color=payload.color,
                text_color=payload.text_color,
                position=payload.position,
                label=payload.label,
            )
        except IntegrationError as error:
            raise _error(error) from error
        return _read(use_cases, profile.tenant_id)

    @router.get("/leads/{lead_id}/deliveries", response_model=list[DeliveryRead])
    def lead_deliveries(
        lead_id: UUID,
        profile: ReaderDep,
        use_cases: Annotated[IntegrationUseCases, Depends(use_cases_factory)],
    ) -> list[DeliveryRead]:
        return [
            delivery_read(item)
            for item in use_cases.deliveries.for_lead(profile.tenant_id, lead_id)
        ]

    @router.get("/widget/v1/{public_id}", response_model=PublicWidgetRead)
    def public_widget(
        public_id: str,
        response: Response,
        use_case: Annotated[GetPublicWidget, Depends(public_widget_factory)],
    ) -> PublicWidgetRead:
        """Public and cacheable: any website may read it (GET only, no credentials)."""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Cache-Control"] = "public, max-age=300"
        widget = use_case.execute(public_id)
        if widget is None:
            raise ApiError(404, "widget_not_found")
        return PublicWidgetRead(
            agency_name=widget.agency_name,
            phone=widget.phone,
            color=widget.color,
            text_color=widget.text_color,
            position=widget.position,
            label=widget.label,
        )

    return router
