"""C4 "Recordatorios y cobros" (the policy, the templates with their Meta status, the
WhatsApp number and this month's count), and the backoffice's part of C5 for Day 9:
template statuses, the last reminder errors and "Planificar ahora"."""

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from followup_core.identity.domain.profile import Profile
from followup_core.tenancy.application.get_tenant import GetTenant
from followup_core.tenancy.domain.errors import TenantNotFoundError
from followup_platform.http_errors import ApiError
from pydantic import BaseModel, Field

from ..auth import current_profile, require_editor, require_platform_admin
from .application.planner import PlanReminders
from .application.settings import GetReminderSettings, ReminderSettings, SaveReminderPolicy
from .application.templates import SaveTemplateText
from .domain.events import Outcome, ReminderEvent
from .domain.policy import (
    ReminderPolicyError,
    ReminderStep,
    SendWindow,
    StepKind,
    TemplateKind,
    WindowPreset,
)
from .domain.templates import TemplateError, TemplateStatus, render, sample_values

ProfileDep = Annotated[Profile, Depends(current_profile)]
EditorDep = Annotated[Profile, Depends(require_editor)]
AdminDep = Annotated[Profile, Depends(require_platform_admin)]

TemplateKindName = Literal["before", "due", "after", "several"]
StatusName = Literal[
    "approved",
    "pending",
    "rejected",
    "paused",
    "disabled",
    "not_submitted",
    "submit_failed",
    "other",
]

KIND_LABELS = {
    TemplateKind.BEFORE: "Antes del vencimiento",
    TemplateKind.DUE: "El día del vencimiento",
    TemplateKind.AFTER: "Después del vencimiento",
    TemplateKind.SEVERAL: "Varias facturas del mismo cliente",
}
# Meta's rejection reasons (its codes), in plain Spanish.
REJECTION_REASONS = {
    "INVALID_FORMAT": "el formato no es válido",
    "TAG_CONTENT_MISMATCH": "el texto no coincide con la categoría de mensaje",
    "ABUSIVE_CONTENT": "Meta lo consideró contenido abusivo",
    "SCAM": "Meta lo consideró engañoso",
    "PROMOTIONAL": "parece un mensaje promocional",
    "INCORRECT_CATEGORY": "la categoría no corresponde",
}
SKIP_LABELS = {
    "invoice_closed": "La factura ya no estaba pendiente",
    "promised": "El cliente prometió pagar",
    "no_whatsapp": "El cliente no tiene WhatsApp",
    "opted_out": "El cliente está marcado “No enviar recordatorios”",
    "not_connected": "WhatsApp no está conectado",
    "connection_error": "La conexión de WhatsApp tiene un error",
    "template_not_approved": "La plantilla no está aprobada",
    "window_closed": "Terminó el horario de envío",
    "already_sent_today": "Ya recibió un recordatorio hoy",
    "tenant_suspended": "El negocio está suspendido",
}


def step_label(step: ReminderStep) -> str:
    days = abs(step.offset_days)
    count = "1 día" if days == 1 else f"{days} días"
    if step.offset_days < 0:
        when = f"{count} antes"
    elif step.offset_days == 0:
        when = "El día del vencimiento"
    else:
        when = f"{count} después"
    return f"{when}: avisar al dueño" if step.escalates else when


def status_name(status: str) -> StatusName:
    value = status.upper()
    if value == "IN_APPEAL":
        return "pending"
    known = {item.value: item for item in TemplateStatus}
    if value in known:
        return known[value].value.lower()  # type: ignore[return-value]
    return "other"


def status_label(status: str, reason: str | None) -> str:
    name = status_name(status)
    if name == "approved":
        return "aprobada"
    if name == "pending":
        return "en revisión"
    if name == "rejected":
        detail = REJECTION_REASONS.get((reason or "").upper(), reason)
        return f"rechazada: {detail}" if detail else "rechazada"
    if name == "paused":
        return "pausada por Meta"
    if name == "disabled":
        return "deshabilitada por Meta"
    if name == "not_submitted":
        return "se envía a Meta cuando conectes WhatsApp"
    if name == "submit_failed":
        return "no se pudo enviar a Meta"
    return status.lower()


class StepRead(BaseModel):
    id: UUID
    offset_days: int
    kind: Literal["reminder", "escalate"]
    template_kind: Literal["before", "due", "after"] | None
    active: bool
    # "3 días antes", "El día del vencimiento", "15 días después: avisar al dueño".
    label: str


class WindowRead(BaseModel):
    preset: Literal["team", "mornings", "business_day", "custom"]
    # "09:00"; only for custom.
    start: str | None
    end: str | None


class TemplateRead(BaseModel):
    kind: TemplateKindName
    label: str
    # With named fields: "Hola {cliente}, ..." (what the owner edits).
    body: str
    # The same text with sample values (C4's preview).
    preview: str
    version: int | None
    status: StatusName
    # "aprobada", "en revisión", "rechazada: <motivo>".
    status_label: str
    rejection_reason: str | None
    # The version that goes out today (None: nothing approved yet).
    in_use_version: int | None
    # A newer version is in review; the approved one keeps going out.
    newer_in_review: bool


class WhatsAppSummaryRead(BaseModel):
    status: Literal["connected", "disconnected", "error", "not_connected"]
    display_phone_number: str | None


class ReminderSettingsRead(BaseModel):
    steps: list[StepRead]
    window: WindowRead
    skip_holidays: bool
    pause_on_promise: bool
    # False until the owner saves the policy once (onboarding or C4).
    configured: bool
    templates: list[TemplateRead]
    whatsapp: WhatsAppSummaryRead
    # Template messages sent this month (Meta charges each one).
    month_count: int
    upcoming_holidays: list[date]
    fields: list[str]


class StepWrite(BaseModel):
    id: UUID | None = None
    offset_days: int = Field(ge=-30, le=90)
    kind: Literal["reminder", "escalate"] = "reminder"
    template_kind: Literal["before", "due", "after"] | None = None
    active: bool = True


class WindowWrite(BaseModel):
    preset: Literal["team", "mornings", "business_day", "custom"]
    start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")


class PolicyWrite(BaseModel):
    steps: list[StepWrite] = Field(min_length=1, max_length=8)
    window: WindowWrite
    skip_holidays: bool = True
    pause_on_promise: bool = True


class TemplateWrite(BaseModel):
    body: str = Field(min_length=1, max_length=1024)


class TemplateAdminRead(BaseModel):
    kind: TemplateKindName
    version: int
    name: str
    status: StatusName
    meta_status: str
    status_label: str
    rejection_reason: str | None
    meta_template_id: str | None
    last_synced_at: datetime | None


class ReminderEventRead(BaseModel):
    at: datetime
    day: date
    outcome: Literal["sent", "failed", "skipped", "escalated"]
    reason: str | None
    reason_label: str | None
    invoice_id: UUID | None
    client_id: UUID


class AdminRemindersRead(BaseModel):
    templates: list[TemplateAdminRead]
    errors: list[ReminderEventRead]
    month_count: int
    configured: bool


class PlanResultRead(BaseModel):
    sends: int
    escalated: int
    promises_ended: int
    paused: str | None


def _clock_text(value: time | None) -> str | None:
    return f"{value:%H:%M}" if value else None


def _parse_time(value: str | None) -> time | None:
    if value is None:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ApiError(422, "reminder_policy_invalid", field="window") from error


def settings_read(settings: ReminderSettings) -> ReminderSettingsRead:
    policy = settings.policy
    templates = []
    for view in settings.templates:
        latest, used = view.latest, view.in_use
        status = latest.status if latest else TemplateStatus.NOT_SUBMITTED.value
        reason = latest.rejection_reason if latest else None
        templates.append(
            TemplateRead(
                kind=view.kind.value,  # type: ignore[arg-type]
                label=KIND_LABELS[view.kind],
                body=view.body,
                preview=render(view.body, sample_values(settings.business_name, view.kind)),
                version=latest.version if latest else None,
                status=status_name(status),
                status_label=status_label(status, reason),
                rejection_reason=reason,
                in_use_version=used.version if used else None,
                newer_in_review=bool(used and latest and latest.version > used.version),
            )
        )
    whatsapp = settings.whatsapp
    return ReminderSettingsRead(
        steps=[
            StepRead(
                id=step.id,
                offset_days=step.offset_days,
                kind=step.kind.value,  # type: ignore[arg-type]
                template_kind=step.template_kind.value if step.template_kind else None,  # type: ignore[arg-type]
                active=step.active,
                label=step_label(step),
            )
            for step in policy.steps
        ],
        window=WindowRead(
            preset=policy.window.preset.value,  # type: ignore[arg-type]
            start=_clock_text(policy.window.start),
            end=_clock_text(policy.window.end),
        ),
        skip_holidays=policy.skip_holidays,
        pause_on_promise=policy.pause_on_promise,
        configured=settings.configured,
        templates=templates,
        whatsapp=WhatsAppSummaryRead(
            status=whatsapp.status.value if whatsapp else "not_connected",  # type: ignore[arg-type]
            display_phone_number=whatsapp.display_phone_number if whatsapp else None,
        ),
        month_count=settings.month_count,
        upcoming_holidays=list(settings.upcoming_holidays),
        fields=["cliente", "negocio", "factura", "monto", "vencimiento"],
    )


def _event_read(event: ReminderEvent) -> ReminderEventRead:
    code = (event.reason or "").split(":")[0] or None
    return ReminderEventRead(
        at=event.created_at,
        day=event.day,
        outcome=event.outcome.value,  # type: ignore[arg-type]
        reason=event.reason,
        reason_label=SKIP_LABELS.get(code or "") if code else None,
        invoice_id=event.invoice_id,
        client_id=event.client_id,
    )


def build_reminders_router(
    get_factory: Callable[..., GetReminderSettings],
    save_factory: Callable[..., SaveReminderPolicy],
    template_factory: Callable[..., SaveTemplateText],
    plan_factory: Callable[..., PlanReminders],
    get_tenant_factory: Callable[..., GetTenant],
    events_factory: Callable[..., Callable[[UUID, list[Outcome], int], list[ReminderEvent]]],
    request_sync_factory: Callable[..., Callable[[UUID], bool]],
    admin_audit_factory: Callable[..., Callable[[UUID, UUID], None]],
) -> APIRouter:
    router = APIRouter(tags=["reminders"])

    def require_tenant(tenant_id: UUID, tenants: GetTenant) -> None:
        try:
            tenants.execute(tenant_id)
        except TenantNotFoundError as error:
            raise ApiError(404, "tenant_not_found") from error

    @router.get("/reminders", response_model=ReminderSettingsRead)
    def get_settings(
        profile: ProfileDep, get: Annotated[GetReminderSettings, Depends(get_factory)]
    ) -> ReminderSettingsRead:
        return settings_read(get.execute(profile.tenant_id))

    @router.put("/reminders", response_model=ReminderSettingsRead)
    def save_policy(
        payload: PolicyWrite,
        profile: EditorDep,
        save: Annotated[SaveReminderPolicy, Depends(save_factory)],
        get: Annotated[GetReminderSettings, Depends(get_factory)],
    ) -> ReminderSettingsRead:
        try:
            steps = [
                ReminderStep(
                    offset_days=item.offset_days,
                    kind=StepKind(item.kind),
                    active=item.active,
                    template_kind=TemplateKind(item.template_kind) if item.template_kind else None,
                    **({"id": item.id} if item.id else {}),
                )
                for item in payload.steps
            ]
            window = SendWindow(
                WindowPreset(payload.window.preset),
                _parse_time(payload.window.start),
                _parse_time(payload.window.end),
            )
            save.execute(
                profile.tenant_id,
                profile.id,
                steps,
                window,
                payload.skip_holidays,
                payload.pause_on_promise,
            )
        except ReminderPolicyError as error:
            raise ApiError(422, "reminder_policy_invalid", field=error.field) from error
        return settings_read(get.execute(profile.tenant_id))

    @router.put("/reminders/templates/{kind}", response_model=ReminderSettingsRead)
    def save_template(
        kind: TemplateKindName,
        payload: TemplateWrite,
        profile: EditorDep,
        save: Annotated[SaveTemplateText, Depends(template_factory)],
        get: Annotated[GetReminderSettings, Depends(get_factory)],
    ) -> ReminderSettingsRead:
        try:
            save.execute(profile.tenant_id, profile.id, TemplateKind(kind), payload.body)
        except TemplateError as error:
            raise ApiError(422, "template_invalid", field=error.field) from error
        return settings_read(get.execute(profile.tenant_id))

    @router.get("/admin/tenants/{tenant_id}/reminders", response_model=AdminRemindersRead)
    def admin_reminders(
        tenant_id: UUID,
        _admin: AdminDep,
        get: Annotated[GetReminderSettings, Depends(get_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
        events: Annotated[
            Callable[[UUID, list[Outcome], int], list[ReminderEvent]], Depends(events_factory)
        ],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> AdminRemindersRead:
        require_tenant(tenant_id, tenants)
        settings = get.execute(tenant_id)
        rows = []
        for view in settings.templates:
            if view.latest is None:
                continue
            for template in [view.latest] + (
                [view.in_use] if view.in_use and view.in_use.id != view.latest.id else []
            ):
                rows.append(
                    TemplateAdminRead(
                        kind=template.kind.value,  # type: ignore[arg-type]
                        version=template.version,
                        name=template.name,
                        status=status_name(template.status),
                        meta_status=template.status,
                        status_label=status_label(template.status, template.rejection_reason),
                        rejection_reason=template.rejection_reason,
                        meta_template_id=template.meta_template_id,
                        last_synced_at=template.last_synced_at,
                    )
                )
        return AdminRemindersRead(
            templates=rows,
            errors=[
                _event_read(event)
                for event in events(tenant_id, [Outcome.FAILED, Outcome.SKIPPED], limit)
            ],
            month_count=settings.month_count,
            configured=settings.configured,
        )

    @router.post("/admin/tenants/{tenant_id}/reminders/plan", response_model=PlanResultRead)
    def admin_plan(
        tenant_id: UUID,
        admin: AdminDep,
        planner: Annotated[PlanReminders, Depends(plan_factory)],
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
        record: Annotated[Callable[[UUID, UUID], None], Depends(admin_audit_factory)],
    ) -> PlanResultRead:
        """ "Planificar ahora": runs the planner for this business right away."""
        require_tenant(tenant_id, tenants)
        result = planner.execute(tenant_id)
        record(tenant_id, admin.id)
        return PlanResultRead(
            sends=result.sends,
            escalated=result.escalated,
            promises_ended=result.promises_ended,
            paused=result.paused,
        )

    @router.post(
        "/admin/tenants/{tenant_id}/reminders/templates/sync",
        response_model=dict[str, bool],
        status_code=202,
    )
    def admin_sync(
        tenant_id: UUID,
        _admin: AdminDep,
        tenants: Annotated[GetTenant, Depends(get_tenant_factory)],
        request_sync: Annotated[Callable[[UUID], bool], Depends(request_sync_factory)],
    ) -> dict[str, bool]:
        """ "Actualizar estados": asks Meta for the templates' status now (a job)."""
        require_tenant(tenant_id, tenants)
        return {"queued": request_sync(tenant_id)}

    return router
