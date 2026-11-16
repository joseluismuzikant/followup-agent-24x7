"""The audit log: what happened to a tenant, who did it, and when. Shown in the backoffice
(S9 Actividad). Details only ever hold ids, counts, codes and versions, never personal data
(names, emails, phones, message text): the allowlist below enforces it."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol
from uuid import UUID, uuid4

from .errors import InvalidAuditDetailsError


class ActorKind(StrEnum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class AuditAction(StrEnum):
    SIGN_UP = "sign_up"
    TENANT_CREATED_BY_ADMIN = "tenant_created_by_admin"
    OWNER_CLAIMED = "owner_claimed"
    AGENT_CONFIG_SAVED = "agent_config_saved"
    PROPERTIES_IMPORTED = "properties_imported"
    WHATSAPP_CONNECTED = "whatsapp_connected"
    WHATSAPP_DISCONNECTED = "whatsapp_disconnected"
    WHATSAPP_ERROR = "whatsapp_error"
    WHATSAPP_RECOVERED = "whatsapp_recovered"
    WHATSAPP_SIGNUP_FAILED = "whatsapp_signup_failed"
    WHATSAPP_SIGNUP_ABANDONED = "whatsapp_signup_abandoned"
    WHATSAPP_ACCOUNT_UPDATE = "whatsapp_account_update"
    WEBHOOK_FAILURE = "webhook_failure"
    SEND_FAILURE = "send_failure"
    TENANT_SUSPENDED = "tenant_suspended"
    TENANT_REACTIVATED = "tenant_reactivated"
    RECONNECT_LINK_SENT = "reconnect_link_sent"
    LLM_COST_ALERT = "llm_cost_alert"
    OWNER_INVITED = "owner_invited"
    INVITATION_RESENT = "invitation_resent"
    TEMPORARY_PASSWORD_RESET = "temporary_password_reset"
    INVITATION_ACCEPTED = "invitation_accepted"


# Ids, counts, codes, versions and enum-like values only.
ALLOWED_DETAIL_KEYS = frozenset(
    {
        "version",
        "created",
        "updated",
        "failed",
        "total",
        "recipients",
        "code",
        "meta_code",
        "step",
        "event",
        "state",
        "status",
        "source",
        "phone_number_id",
        "waba_id",
        "import_id",
        "month",
        "cost_usd",
        "skipped",
        "client_id",
        "invoice_id",
        "paid_via",
        # Cuentas Claras reminders: a promise's date, a template kind, a step count, the
        # send window's preset, whether transfer details were removed.
        "promised_until",
        "kind",
        "steps",
        "window",
        "removed",
    }
)


def _check(details: Mapping[str, Any]) -> None:
    unknown = set(details) - ALLOWED_DETAIL_KEYS
    if unknown:
        raise InvalidAuditDetailsError(f"Audit details not allowed: {sorted(unknown)}")
    for value in details.values():
        if not isinstance(value, str | int | bool) and value is not None:
            raise InvalidAuditDetailsError("Audit details are flat ids, counts and codes.")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    tenant_id: UUID
    at: datetime
    actor_kind: ActorKind
    # One of core's AuditAction values or a product's own (a StrEnum of the product).
    action: str
    details: Mapping[str, Any] = field(default_factory=dict)
    actor_profile_id: UUID | None = None
    # System failures repeat; one event per key (e.g. per tenant, code and hour) is enough.
    dedupe_key: str | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _check(self.details)
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


def hourly_key(action: str, tenant_id: UUID, code: str, at: datetime) -> str:
    return f"{action}:{tenant_id}:{code}:{at:%Y%m%d%H}"


class AuditLog(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Adds the event in the caller's transaction (dropped if its dedupe key exists)."""
        ...

    def latest(self, tenant_id: UUID, limit: int) -> Sequence[AuditEvent]: ...


class NoAuditLog:
    """For use cases built without an audit log (unit tests, scripts)."""

    def record(self, event: AuditEvent) -> None:
        return None

    def latest(self, tenant_id: UUID, limit: int) -> Sequence[AuditEvent]:
        return ()
