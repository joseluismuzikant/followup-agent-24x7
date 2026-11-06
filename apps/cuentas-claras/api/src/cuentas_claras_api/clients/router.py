"""Clientes: the companies that owe the invoices (list, detail with its invoices, create and
edit)."""

from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from math import ceil
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from followup_core.identity.domain.profile import Profile
from followup_core.messaging.domain.phones import display as phone_display
from followup_platform.http_errors import ApiError
from pydantic import BaseModel, Field

from ..auth import current_profile, require_editor
from ..invoices.domain.invoice import Invoice
from ..invoices.domain.repository import InvoiceRepository
from ..invoices.domain.status import display_status, today_in
from .application.clients import PAGE_SIZE, CreateClient, GetClient, ListClients, UpdateClient
from .domain.client import Client, ClientFields
from .domain.cuit import format_cuit
from .domain.errors import ClientInvalidError, ClientNotFoundError, CuitInvalidError, CuitTakenError
from .domain.repository import ClientBalance

ProfileDep = Annotated[Profile, Depends(current_profile)]
EditorDep = Annotated[Profile, Depends(require_editor)]


class ClientRead(BaseModel):
    id: UUID
    name: str
    subtitle: str | None
    # Shown as 30-12345678-9; null when the client has none.
    cuit: str | None
    contact_name: str | None
    # E.164, and the Argentine way to show it.
    whatsapp: str | None
    whatsapp_display: str | None
    email: str | None
    notes: str | None
    active: bool
    missing_whatsapp: bool
    open_invoices: int
    # Decimal amounts as strings ("180000.50"), never floats.
    owed_ars: str
    owed_usd: str
    created_at: datetime


class ClientListRead(BaseModel):
    items: list[ClientRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class ClientInvoiceRead(BaseModel):
    id: UUID
    number: str
    due_date: date
    amount: str
    currency: str
    status: str
    status_label: str


class ClientDetailRead(ClientRead):
    invoices: list[ClientInvoiceRead]


class ClientWrite(BaseModel):
    name: str = Field(max_length=200)
    subtitle: str = Field(default="", max_length=200)
    cuit: str = Field(default="", max_length=20)
    contact_name: str = Field(default="", max_length=200)
    whatsapp: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=320)
    notes: str = Field(default="", max_length=2000)


class ClientUpdate(ClientWrite):
    active: bool | None = None


def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def client_read(balance: ClientBalance) -> ClientRead:
    client = balance.client
    return ClientRead(**_client_fields(client, balance))


def _client_fields(client: Client, balance: ClientBalance) -> dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "subtitle": client.subtitle,
        "cuit": format_cuit(client.cuit) if client.cuit else None,
        "contact_name": client.contact_name,
        "whatsapp": client.whatsapp,
        "whatsapp_display": phone_display(client.whatsapp) if client.whatsapp else None,
        "email": client.email,
        "notes": client.notes,
        "active": client.active,
        "missing_whatsapp": client.missing_whatsapp,
        "open_invoices": balance.open_invoices,
        "owed_ars": _money(balance.owed_ars),
        "owed_usd": _money(balance.owed_usd),
        "created_at": client.created_at,
    }


def _fields(payload: ClientWrite) -> ClientFields:
    return ClientFields(
        name=payload.name,
        subtitle=payload.subtitle,
        cuit=payload.cuit,
        contact_name=payload.contact_name,
        whatsapp=payload.whatsapp,
        email=payload.email,
        notes=payload.notes,
    )


def _invoice_read(invoice: Invoice, today: date) -> ClientInvoiceRead:
    status = display_status(invoice, today)
    return ClientInvoiceRead(
        id=invoice.id,
        number=invoice.display_number,
        due_date=invoice.due_date,
        amount=_money(invoice.amount),
        currency=invoice.currency.value,
        status=status.kind.value,
        status_label=status.label,
    )


def build_clients_router(
    list_factory: Callable[..., ListClients],
    get_factory: Callable[..., GetClient],
    create_factory: Callable[..., CreateClient],
    update_factory: Callable[..., UpdateClient],
    invoices_factory: Callable[..., InvoiceRepository],
    timezone_factory: Callable[..., Callable[[UUID], str]],
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(tags=["clients"])

    def detail(
        balance: ClientBalance, invoices: InvoiceRepository, timezone: str
    ) -> ClientDetailRead:
        today = today_in(timezone, clock())
        rows = invoices.for_client(balance.client.tenant_id, balance.client.id)
        return ClientDetailRead(
            **_client_fields(balance.client, balance),
            invoices=[_invoice_read(invoice, today) for invoice in rows],
        )

    def invalid(error: Exception) -> ApiError:
        if isinstance(error, CuitInvalidError):
            return ApiError(422, "cuit_invalid")
        if isinstance(error, CuitTakenError):
            return ApiError(409, "cuit_taken")
        if isinstance(error, ClientInvalidError):
            return ApiError(422, "client_invalid", field=error.field)
        return ApiError(404, "client_not_found")

    @router.get("/clients", response_model=ClientListRead)
    def list_clients(
        profile: ProfileDep,
        use_case: Annotated[ListClients, Depends(list_factory)],
        q: Annotated[str, Query(max_length=100)] = "",
        missing_whatsapp: bool = False,
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> ClientListRead:
        result = use_case.execute(profile.tenant_id, q, missing_whatsapp, page)
        return ClientListRead(
            items=[client_read(item) for item in result.items],
            total=result.total,
            page=result.page,
            page_size=PAGE_SIZE,
            total_pages=ceil(result.total / PAGE_SIZE) if result.total else 0,
        )

    @router.post("/clients", response_model=ClientDetailRead, status_code=201)
    def create_client(
        payload: ClientWrite,
        profile: EditorDep,
        use_case: Annotated[CreateClient, Depends(create_factory)],
        get: Annotated[GetClient, Depends(get_factory)],
        invoices: Annotated[InvoiceRepository, Depends(invoices_factory)],
        timezone_of: Annotated[Callable[[UUID], str], Depends(timezone_factory)],
    ) -> ClientDetailRead:
        try:
            client = use_case.execute(profile.tenant_id, profile.id, _fields(payload))
        except (CuitInvalidError, CuitTakenError, ClientInvalidError) as error:
            raise invalid(error) from error
        return detail(
            get.execute(profile.tenant_id, client.id), invoices, timezone_of(profile.tenant_id)
        )

    @router.get("/clients/{client_id}", response_model=ClientDetailRead)
    def get_client(
        client_id: UUID,
        profile: ProfileDep,
        get: Annotated[GetClient, Depends(get_factory)],
        invoices: Annotated[InvoiceRepository, Depends(invoices_factory)],
        timezone_of: Annotated[Callable[[UUID], str], Depends(timezone_factory)],
    ) -> ClientDetailRead:
        try:
            balance = get.execute(profile.tenant_id, client_id)
        except ClientNotFoundError as error:
            raise ApiError(404, "client_not_found") from error
        return detail(balance, invoices, timezone_of(profile.tenant_id))

    @router.patch("/clients/{client_id}", response_model=ClientDetailRead)
    def update_client(
        client_id: UUID,
        payload: ClientUpdate,
        profile: EditorDep,
        use_case: Annotated[UpdateClient, Depends(update_factory)],
        get: Annotated[GetClient, Depends(get_factory)],
        invoices: Annotated[InvoiceRepository, Depends(invoices_factory)],
        timezone_of: Annotated[Callable[[UUID], str], Depends(timezone_factory)],
    ) -> ClientDetailRead:
        try:
            use_case.execute(
                profile.tenant_id, profile.id, client_id, _fields(payload), payload.active
            )
        except (CuitInvalidError, CuitTakenError, ClientInvalidError, ClientNotFoundError) as error:
            raise invalid(error) from error
        return detail(
            get.execute(profile.tenant_id, client_id), invoices, timezone_of(profile.tenant_id)
        )

    return router
