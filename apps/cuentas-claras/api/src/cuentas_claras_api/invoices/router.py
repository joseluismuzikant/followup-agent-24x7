"""Facturas (C2) and Inicio's summary: list with tabs, counts, search and pagination; detail;
manual create and edit; "Marcar como pagada" and "Anular"; the CSV/XLSX import with its
report and error download, and the template."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from followup_core.identity.domain.profile import Profile
from followup_platform.http_errors import ApiError
from pydantic import BaseModel, Field

from ..auth import current_profile, require_editor
from ..clients.domain.cuit import format_cuit
from ..clients.domain.errors import ClientNotFoundError
from ..clients.router import ClientRead
from ..reminders.domain.next_action import NextAction
from .application.imports import GetImportErrors, ImportInvoices, import_template
from .application.invoices import (
    PAGE_SIZE,
    CancelInvoice,
    CreateInvoice,
    GetInvoice,
    GetSummary,
    InvoiceView,
    ListInvoices,
    MarkInvoicePaid,
    PromiseInvoice,
    RemovePromise,
    UpdateInvoice,
)
from .domain.errors import (
    ImportFileInvalidError,
    ImportNotFoundError,
    ImportTooLargeError,
    InvoiceAlreadyPaidError,
    InvoiceInvalidError,
    InvoiceNotFoundError,
    InvoiceNumberTakenError,
)
from .domain.imports import MAX_IMPORT_BYTES, InvoiceImport
from .domain.invoice import PAID_VIA_LABELS, Currency, Invoice, InvoiceFields, PaidVia
from .domain.number import InvoiceType
from .domain.repository import Amounts, InvoiceRow, Tab
from .domain.status import display_status

ProfileDep = Annotated[Profile, Depends(current_profile)]
EditorDep = Annotated[Profile, Depends(require_editor)]
StatusKind = Literal["paid", "overdue", "due_soon", "pending", "promised", "cancelled"]
NextActions = Callable[[UUID, Sequence[Invoice]], Mapping[UUID, NextAction]]
RequestPlan = Callable[[UUID], bool]


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


class DisplayStatusRead(BaseModel):
    kind: StatusKind
    # "Vencida · 12 días", "Por vencer", "Pagada · Mercado Pago".
    label: str
    days_overdue: int | None


class InvoiceListItemRead(BaseModel):
    id: UUID
    client_id: UUID
    client_name: str
    client_subtitle: str | None
    # "B 0003-00001245"
    number: str
    amount: str
    currency: Literal["ARS", "USD"]
    due_date: date
    status: DisplayStatusRead
    # "Lo próximo": the next scheduled action ("Recordatorio mañana 9:30"); null when the
    # invoice is no longer owed.
    next_action: str | None
    next_action_kind: str | None


class TabCountsRead(BaseModel):
    pending: int
    overdue: int
    promised: int
    paid_this_month: int


class InvoiceListRead(BaseModel):
    items: list[InvoiceListItemRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    counts: TabCountsRead


class PaymentRead(BaseModel):
    paid_at: date
    paid_via: str
    paid_via_label: str
    reference: str | None


class InvoiceDetailRead(BaseModel):
    id: UUID
    number: str
    invoice_type: Literal["A", "B", "C"]
    point_of_sale: int
    invoice_number: int
    issue_date: date
    due_date: date
    amount: str
    currency: Literal["ARS", "USD"]
    description: str
    status: DisplayStatusRead
    lifecycle: Literal["open", "promised", "paid", "cancelled"]
    payment: PaymentRead | None
    cancelled_reason: str | None
    # The day the client promised to pay by.
    promised_until: date | None
    client: ClientRead
    next_action: str | None
    next_action_kind: str | None


class InvoiceWrite(BaseModel):
    client_id: UUID
    invoice_type: Literal["A", "B", "C"]
    point_of_sale: int = Field(ge=1, le=99_999)
    number: int = Field(ge=1, le=99_999_999)
    issue_date: date
    due_date: date
    # A decimal string ("180000.50"), never a float.
    amount: str = Field(max_length=20)
    currency: Literal["ARS", "USD"] = "ARS"
    description: str = Field(default="", max_length=500)


class MarkPaidWrite(BaseModel):
    paid_at: date
    paid_via: Literal["manual", "transfer", "mercado_pago", "other"]
    reference: str | None = Field(default=None, max_length=120)


class CancelWrite(BaseModel):
    reason: str = Field(max_length=500)


class PromiseWrite(BaseModel):
    promised_until: date


class AmountsRead(BaseModel):
    amount: str
    count: int


class SummaryRead(BaseModel):
    to_collect: AmountsRead
    overdue: AmountsRead
    to_collect_usd: AmountsRead
    overdue_usd: AmountsRead


class ImportRowErrorRead(BaseModel):
    row: int
    error: str


class ImportReportRead(BaseModel):
    id: UUID
    file_name: str
    total: int
    created: int
    updated: int
    skipped: int
    failed: int
    errors: list[ImportRowErrorRead]
    warnings: list[str]


def _status(invoice: Invoice, today: date) -> DisplayStatusRead:
    status = display_status(invoice, today)
    return DisplayStatusRead(
        kind=status.kind.value,  # type: ignore[arg-type]
        label=status.label,
        days_overdue=status.days_overdue,
    )


def _item(row: InvoiceRow, today: date, action: NextAction | None) -> InvoiceListItemRead:
    invoice = row.invoice
    return InvoiceListItemRead(
        id=invoice.id,
        client_id=invoice.client_id,
        client_name=row.client_name,
        client_subtitle=row.client_subtitle,
        number=invoice.display_number,
        amount=_money(invoice.amount),
        currency=invoice.currency.value,  # type: ignore[arg-type]
        due_date=invoice.due_date,
        status=_status(invoice, today),
        next_action=action.label if action else None,
        next_action_kind=action.kind.value if action else None,
    )


def _detail(view: InvoiceView, action: NextAction | None = None) -> InvoiceDetailRead:
    invoice, client = view.invoice, view.client
    payment = None
    if invoice.paid_at is not None and invoice.paid_via is not None:
        payment = PaymentRead(
            paid_at=invoice.paid_at,
            paid_via=invoice.paid_via.value,
            paid_via_label=PAID_VIA_LABELS[invoice.paid_via],
            reference=invoice.payment_reference,
        )
    return InvoiceDetailRead(
        id=invoice.id,
        number=invoice.display_number,
        invoice_type=invoice.invoice_type.value,  # type: ignore[arg-type]
        point_of_sale=invoice.point_of_sale,
        invoice_number=invoice.number,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        amount=_money(invoice.amount),
        currency=invoice.currency.value,  # type: ignore[arg-type]
        description=invoice.description,
        status=_status(invoice, view.today),
        lifecycle=invoice.status.value,  # type: ignore[arg-type]
        payment=payment,
        cancelled_reason=invoice.cancelled_reason,
        promised_until=invoice.promised_until,
        client=ClientRead(
            id=client.id,
            name=client.name,
            subtitle=client.subtitle,
            cuit=format_cuit(client.cuit) if client.cuit else None,
            contact_name=client.contact_name,
            whatsapp=client.whatsapp,
            whatsapp_display=None,
            email=client.email,
            notes=client.notes,
            active=client.active,
            missing_whatsapp=client.missing_whatsapp,
            no_reminders=client.no_reminders,
            open_invoices=0,
            owed_ars="0.00",
            owed_usd="0.00",
            created_at=client.created_at,
        ),
        next_action=action.label if action else None,
        next_action_kind=action.kind.value if action else None,
    )


def _fields(payload: InvoiceWrite) -> InvoiceFields:
    try:
        amount = Decimal(payload.amount)
    except InvalidOperation as error:
        raise ApiError(422, "invoice_invalid", field="amount") from error
    return InvoiceFields(
        client_id=payload.client_id,
        invoice_type=InvoiceType(payload.invoice_type),
        point_of_sale=payload.point_of_sale,
        number=payload.number,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        amount=amount,
        currency=Currency(payload.currency),
        description=payload.description,
    )


def _amounts(amounts: Amounts) -> AmountsRead:
    return AmountsRead(amount=_money(amounts.amount), count=amounts.count)


def import_report(record: InvoiceImport) -> ImportReportRead:
    return ImportReportRead(
        id=record.id,
        file_name=record.file_name,
        total=record.total,
        created=record.created,
        updated=record.updated,
        skipped=record.skipped,
        failed=record.failed,
        errors=[ImportRowErrorRead(row=row.row, error=row.error) for row in record.failed_rows],
        warnings=list(record.warnings),
    )


def _csv_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def build_invoices_router(
    list_factory: Callable[..., ListInvoices],
    get_factory: Callable[..., GetInvoice],
    create_factory: Callable[..., CreateInvoice],
    update_factory: Callable[..., UpdateInvoice],
    mark_paid_factory: Callable[..., MarkInvoicePaid],
    cancel_factory: Callable[..., CancelInvoice],
    summary_factory: Callable[..., GetSummary],
    import_factory: Callable[..., ImportInvoices],
    import_errors_factory: Callable[..., GetImportErrors],
    promise_factory: Callable[..., PromiseInvoice],
    remove_promise_factory: Callable[..., RemovePromise],
    next_actions_factory: Callable[..., NextActions],
    request_plan_factory: Callable[..., RequestPlan],
) -> APIRouter:
    """Every change to an invoice plans the business's reminders again (a job, a minute
    later at most)."""
    router = APIRouter(tags=["invoices"])

    def detail(view: InvoiceView, next_actions: NextActions) -> InvoiceDetailRead:
        actions = next_actions(view.invoice.tenant_id, [view.invoice])
        return _detail(view, actions.get(view.invoice.id))

    def failure(error: Exception) -> ApiError:
        if isinstance(error, InvoiceNotFoundError):
            return ApiError(404, "invoice_not_found")
        if isinstance(error, ClientNotFoundError):
            return ApiError(404, "client_not_found")
        if isinstance(error, InvoiceNumberTakenError):
            return ApiError(409, "invoice_number_taken")
        if isinstance(error, InvoiceAlreadyPaidError):
            return ApiError(409, "invoice_already_paid")
        if isinstance(error, InvoiceInvalidError):
            return ApiError(422, "invoice_invalid", field=error.field)
        raise error

    known = (
        InvoiceNotFoundError,
        ClientNotFoundError,
        InvoiceNumberTakenError,
        InvoiceAlreadyPaidError,
        InvoiceInvalidError,
    )

    @router.get("/invoices", response_model=InvoiceListRead)
    def list_invoices(
        profile: ProfileDep,
        use_case: Annotated[ListInvoices, Depends(list_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
        tab: Tab = Tab.PENDING,
        q: Annotated[str, Query(max_length=100)] = "",
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> InvoiceListRead:
        result = use_case.execute(profile.tenant_id, tab, q, page)
        today = use_case.today(profile.tenant_id)
        actions = next_actions(profile.tenant_id, [row.invoice for row in result.rows])
        return InvoiceListRead(
            items=[_item(row, today, actions.get(row.invoice.id)) for row in result.rows],
            total=result.total,
            page=page,
            page_size=PAGE_SIZE,
            total_pages=ceil(result.total / PAGE_SIZE) if result.total else 0,
            counts=TabCountsRead(**{key.value: value for key, value in result.counts.items()}),
        )

    @router.get("/summary", response_model=SummaryRead)
    def summary(
        profile: ProfileDep, use_case: Annotated[GetSummary, Depends(summary_factory)]
    ) -> SummaryRead:
        result = use_case.execute(profile.tenant_id)
        return SummaryRead(
            to_collect=_amounts(result.to_collect),
            overdue=_amounts(result.overdue),
            to_collect_usd=_amounts(result.to_collect_usd),
            overdue_usd=_amounts(result.overdue_usd),
        )

    # Declared before /invoices/{invoice_id}, which would otherwise take these as ids.
    @router.get(
        "/invoices/import-template.csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def template(_profile: ProfileDep) -> Response:
        return _csv_response(import_template(), "plantilla-facturas.csv")

    @router.post("/invoices/import", response_model=ImportReportRead)
    def import_invoices(
        file: Annotated[UploadFile, File()],
        profile: EditorDep,
        use_case: Annotated[ImportInvoices, Depends(import_factory)],
        request_plan: Annotated[RequestPlan, Depends(request_plan_factory)],
    ) -> ImportReportRead:
        content = file.file.read(MAX_IMPORT_BYTES + 1)
        try:
            record = use_case.execute(
                profile.tenant_id, profile.id, file.filename or "facturas.csv", content
            )
        except ImportTooLargeError as error:
            raise ApiError(413, "import_too_large") from error
        except ImportFileInvalidError as error:
            raise ApiError(422, "import_file_invalid") from error
        request_plan(profile.tenant_id)
        return import_report(record)

    @router.get(
        "/invoices/import/{import_id}/errors.csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def import_errors(
        import_id: UUID,
        profile: ProfileDep,
        use_case: Annotated[GetImportErrors, Depends(import_errors_factory)],
    ) -> Response:
        try:
            content = use_case.execute(profile.tenant_id, import_id)
        except ImportNotFoundError as error:
            raise ApiError(404, "import_not_found") from error
        return _csv_response(content, "facturas-con-errores.csv")

    @router.post("/invoices", response_model=InvoiceDetailRead, status_code=201)
    def create_invoice(
        payload: InvoiceWrite,
        profile: EditorDep,
        use_case: Annotated[CreateInvoice, Depends(create_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
        request_plan: Annotated[RequestPlan, Depends(request_plan_factory)],
    ) -> InvoiceDetailRead:
        try:
            view = use_case.execute(profile.tenant_id, profile.id, _fields(payload))
        except known as error:
            raise failure(error) from error
        request_plan(profile.tenant_id)
        return detail(view, next_actions)

    @router.get("/invoices/{invoice_id}", response_model=InvoiceDetailRead)
    def get_invoice(
        invoice_id: UUID,
        profile: ProfileDep,
        use_case: Annotated[GetInvoice, Depends(get_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
    ) -> InvoiceDetailRead:
        try:
            view = use_case.execute(profile.tenant_id, invoice_id)
        except known as error:
            raise failure(error) from error
        return detail(view, next_actions)

    @router.patch("/invoices/{invoice_id}", response_model=InvoiceDetailRead)
    def update_invoice(
        invoice_id: UUID,
        payload: InvoiceWrite,
        profile: EditorDep,
        use_case: Annotated[UpdateInvoice, Depends(update_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
        request_plan: Annotated[RequestPlan, Depends(request_plan_factory)],
    ) -> InvoiceDetailRead:
        try:
            view = use_case.execute(profile.tenant_id, profile.id, invoice_id, _fields(payload))
        except known as error:
            raise failure(error) from error
        request_plan(profile.tenant_id)
        return detail(view, next_actions)

    @router.post("/invoices/{invoice_id}/mark-paid", response_model=InvoiceDetailRead)
    def mark_paid(
        invoice_id: UUID,
        payload: MarkPaidWrite,
        profile: EditorDep,
        use_case: Annotated[MarkInvoicePaid, Depends(mark_paid_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
    ) -> InvoiceDetailRead:
        try:
            view = use_case.execute(
                profile.tenant_id,
                profile.id,
                invoice_id,
                payload.paid_at,
                PaidVia(payload.paid_via),
                payload.reference,
            )
        except known as error:
            raise failure(error) from error
        # A paid invoice drops out of the planner by itself; the send job checks again.
        return detail(view, next_actions)

    @router.post("/invoices/{invoice_id}/cancel", response_model=InvoiceDetailRead)
    def cancel(
        invoice_id: UUID,
        payload: CancelWrite,
        profile: EditorDep,
        use_case: Annotated[CancelInvoice, Depends(cancel_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
    ) -> InvoiceDetailRead:
        try:
            view = use_case.execute(profile.tenant_id, profile.id, invoice_id, payload.reason)
        except known as error:
            raise failure(error) from error
        return detail(view, next_actions)

    @router.post("/invoices/{invoice_id}/promise", response_model=InvoiceDetailRead)
    def promise(
        invoice_id: UUID,
        payload: PromiseWrite,
        profile: EditorDep,
        use_case: Annotated[PromiseInvoice, Depends(promise_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
        request_plan: Annotated[RequestPlan, Depends(request_plan_factory)],
    ) -> InvoiceDetailRead:
        """ "Registrar promesa de pago"."""
        try:
            view = use_case.execute(
                profile.tenant_id, profile.id, invoice_id, payload.promised_until
            )
        except known as error:
            raise failure(error) from error
        request_plan(profile.tenant_id)
        return detail(view, next_actions)

    @router.delete("/invoices/{invoice_id}/promise", response_model=InvoiceDetailRead)
    def remove_promise(
        invoice_id: UUID,
        profile: EditorDep,
        use_case: Annotated[RemovePromise, Depends(remove_promise_factory)],
        next_actions: Annotated[NextActions, Depends(next_actions_factory)],
        request_plan: Annotated[RequestPlan, Depends(request_plan_factory)],
    ) -> InvoiceDetailRead:
        """ "Quitar promesa"."""
        try:
            view = use_case.execute(profile.tenant_id, profile.id, invoice_id)
        except known as error:
            raise failure(error) from error
        request_plan(profile.tenant_id)
        return detail(view, next_actions)

    return router
