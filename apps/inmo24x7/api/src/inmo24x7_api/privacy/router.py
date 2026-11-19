"""Backoffice → business page → "Datos y privacidad" (platform admins only)."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from followup_core.identity.domain.profile import Profile
from followup_core.messaging.domain.phones import display, to_e164
from pydantic import BaseModel, Field

from ..auth import require_platform_admin
from ..http_errors import ApiError
from .application import (
    DeleteContactData,
    FindContacts,
    GetClosureSummary,
    RequestAccountClosure,
    SetContactDoNotContact,
)
from .domain import (
    BusinessNotFoundError,
    ClosureSummary,
    ConfirmationMismatchError,
    ContactNotFoundError,
    ContactSummary,
    PhoneInvalidError,
    PlatformBusinessError,
)

AdminDep = Annotated[Profile, Depends(require_platform_admin)]


class ContactRead(BaseModel):
    wa_id: str
    # "+54 9 11 5555-0188": what the admin types to confirm.
    phone: str
    names: list[str]
    leads: int
    messages: int
    visits: int
    last_activity_at: datetime | None
    do_not_contact: bool


class ContactDeleteWrite(BaseModel):
    wa_id: str = Field(min_length=6, max_length=32)
    # The contact's phone, typed again.
    confirmation: str = Field(min_length=1, max_length=40)


class ContactDeletedRead(BaseModel):
    leads: int
    conversations: int
    messages: int
    visits: int


class DoNotContactPhoneWrite(BaseModel):
    phone: str = Field(min_length=6, max_length=40)
    blocked: bool


class DoNotContactPhoneRead(BaseModel):
    wa_id: str
    phone: str
    do_not_contact: bool


class ClosureRead(BaseModel):
    name: str
    properties: int
    leads: int
    conversations: int
    messages: int
    users: int
    users_kept: int
    whatsapp_connected: bool
    # The closing job is pending: the business is already stopped.
    closing: bool


class CloseWrite(BaseModel):
    # The business name, typed again.
    business_name: str = Field(min_length=1, max_length=200)


def _phone(wa_id: str) -> str:
    e164 = to_e164(wa_id)
    return display(e164) if e164 else f"+{wa_id}"


def _contact(item: ContactSummary) -> ContactRead:
    return ContactRead(
        wa_id=item.wa_id,
        phone=_phone(item.wa_id),
        names=list(item.names),
        leads=item.leads,
        messages=item.messages,
        visits=item.visits,
        last_activity_at=item.last_activity_at,
        do_not_contact=item.do_not_contact,
    )


def _closure(summary: ClosureSummary) -> ClosureRead:
    return ClosureRead(
        name=summary.name,
        properties=summary.properties,
        leads=summary.leads,
        conversations=summary.conversations,
        messages=summary.messages,
        users=summary.users,
        users_kept=summary.users_kept,
        whatsapp_connected=summary.whatsapp_connected,
        closing=summary.closing,
    )


@contextmanager
def _errors() -> Iterator[None]:
    try:
        yield
    except BusinessNotFoundError as error:
        raise ApiError(404, "tenant_not_found") from error
    except ContactNotFoundError as error:
        raise ApiError(404, "contact_not_found") from error
    except ConfirmationMismatchError as error:
        raise ApiError(422, "confirmation_mismatch") from error
    except PhoneInvalidError as error:
        raise ApiError(422, "phone_invalid") from error
    except PlatformBusinessError as error:
        raise ApiError(409, "platform_business") from error


def build_privacy_router(
    find_factory: Callable[..., FindContacts],
    delete_factory: Callable[..., DeleteContactData],
    do_not_contact_factory: Callable[..., SetContactDoNotContact],
    summary_factory: Callable[..., GetClosureSummary],
    close_factory: Callable[..., RequestAccountClosure],
) -> APIRouter:
    router = APIRouter(prefix="/admin/tenants/{tenant_id}", tags=["backoffice"])

    @router.get("/contacts", response_model=list[ContactRead])
    def find_contacts(
        tenant_id: UUID,
        _admin: AdminDep,
        use_case: Annotated[FindContacts, Depends(find_factory)],
        q: Annotated[str, Query(max_length=100)] = "",
    ) -> list[ContactRead]:
        """By phone (any format or part of it) or name; what each one's deletion removes."""
        with _errors():
            return [_contact(item) for item in use_case.execute(tenant_id, q)]

    @router.post("/contacts/delete", response_model=ContactDeletedRead)
    def delete_contact(
        tenant_id: UUID,
        payload: ContactDeleteWrite,
        admin: AdminDep,
        use_case: Annotated[DeleteContactData, Depends(delete_factory)],
    ) -> ContactDeletedRead:
        with _errors():
            counts = use_case.execute(admin.id, tenant_id, payload.wa_id, payload.confirmation)
        return ContactDeletedRead(
            leads=counts.leads,
            conversations=counts.threads,
            messages=counts.messages,
            visits=counts.visits,
        )

    @router.post("/do-not-contact", response_model=DoNotContactPhoneRead)
    def set_do_not_contact(
        tenant_id: UUID,
        payload: DoNotContactPhoneWrite,
        admin: AdminDep,
        use_case: Annotated[SetContactDoNotContact, Depends(do_not_contact_factory)],
    ) -> DoNotContactPhoneRead:
        with _errors():
            wa_id = use_case.execute(admin.id, tenant_id, payload.phone, payload.blocked)
        return DoNotContactPhoneRead(
            wa_id=wa_id, phone=_phone(wa_id), do_not_contact=payload.blocked
        )

    @router.get("/closure", response_model=ClosureRead)
    def closure_summary(
        tenant_id: UUID,
        _admin: AdminDep,
        use_case: Annotated[GetClosureSummary, Depends(summary_factory)],
    ) -> ClosureRead:
        with _errors():
            return _closure(use_case.execute(tenant_id))

    @router.post("/close", response_model=ClosureRead, status_code=202)
    def close_account(
        tenant_id: UUID,
        payload: CloseWrite,
        admin: AdminDep,
        use_case: Annotated[RequestAccountClosure, Depends(close_factory)],
    ) -> ClosureRead:
        """Stops the business now; a job deletes its data in the next minutes."""
        with _errors():
            return _closure(use_case.execute(admin.id, tenant_id, payload.business_name))

    return router
