"""What a deletion touches, in counts only: the audit log and the backoffice never see the
deleted values themselves."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from followup_core.messaging.domain.phones import to_e164

# The suspension reason while a closing job is pending (the business is stopped meanwhile).
CLOSING_REASON = "Cierre de cuenta y eliminación de datos en curso."
TOMBSTONE_NAME = "Cuenta eliminada"


class PrivacyError(Exception):
    pass


class BusinessNotFoundError(PrivacyError):
    pass


class ContactNotFoundError(PrivacyError):
    pass


class ConfirmationMismatchError(PrivacyError):
    """The typed phone or business name is not the one being deleted."""


class PhoneInvalidError(PrivacyError):
    pass


class PlatformBusinessError(PrivacyError):
    """The platform admins' own business is never closed from the backoffice."""


@dataclass(frozen=True, slots=True)
class ContactSummary:
    """One WhatsApp contact of a business, as the backoffice shows it before deleting."""

    wa_id: str
    names: tuple[str, ...]
    leads: int
    messages: int
    visits: int
    last_activity_at: datetime | None
    do_not_contact: bool


@dataclass(frozen=True, slots=True)
class ErasedCounts:
    leads: int = 0
    threads: int = 0
    messages: int = 0
    visits: int = 0
    inbound_events: int = 0
    outbound_parts: int = 0
    jobs: int = 0
    checkpoints: int = 0
    llm_calls_unlinked: int = 0


@dataclass(frozen=True, slots=True)
class ClosureSummary:
    """What "Cerrar cuenta y eliminar datos" removes."""

    name: str
    properties: int
    leads: int
    conversations: int
    messages: int
    users: int
    # Users who also belong to a business of the other product: their login stays.
    users_kept: int
    whatsapp_connected: bool
    closing: bool


@dataclass(frozen=True, slots=True)
class ProfileUser:
    user_id: UUID
    email: str
    # True when the person has a profile in another business: only this profile goes.
    keep_login: bool


@dataclass(frozen=True, slots=True)
class TenantErasure:
    counts: ErasedCounts
    properties: int
    users: tuple[ProfileUser, ...] = field(default_factory=tuple)


def wa_id_for(phone: str) -> str | None:
    """The wa_id form of a typed phone ("11 5555-0188" → "5491155550188")."""
    e164 = to_e164(phone)
    return e164.lstrip("+") if e164 else None


def wa_id_variants(wa_id: str) -> list[str]:
    """The same Argentine mobile as Meta may send it, with and without the 9."""
    variants = [wa_id]
    if wa_id.startswith("549") and len(wa_id) == 13:
        variants.append("54" + wa_id[3:])
    return variants


def confirms(typed: str, wa_id: str) -> bool:
    """The admin typed the contact's phone (any common format)."""
    digits = "".join(char for char in typed if char.isdigit())
    return bool(digits) and (wa_id_for(typed) == wa_id or digits == wa_id)
