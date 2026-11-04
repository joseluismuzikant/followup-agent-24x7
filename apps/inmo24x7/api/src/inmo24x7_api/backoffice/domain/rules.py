"""The backoffice's view of a business (S8, S9): its onboarding, WhatsApp badge and whether
it needs help. Pure rules, defined once; the list, the KPIs and the filters all use them."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

ONBOARDING_STUCK_AFTER = timedelta(hours=48)
TRIAL_ENDING_WITHIN = timedelta(days=3)


class WhatsAppBadge(StrEnum):
    CONNECTED = "connected"  # "Conectado"
    VERIFICATION_PENDING = "verification_pending"  # "Verificación pendiente"
    ACTION_REQUIRED = "action_required"  # "Acción requerida"
    NOT_CONNECTED = "not_connected"  # "Sin conectar"


class TenantFilter(StrEnum):
    ALL = "all"
    NEEDS_HELP = "needs_help"
    TRIAL = "trial"


@dataclass(frozen=True, slots=True)
class Onboarding:
    """S9's five: cuenta, agente configurado, agente probado, WhatsApp conectado,
    propiedades propias."""

    agent_configured: bool
    agent_tested: bool
    whatsapp_connected: bool
    own_properties: bool
    finished: bool  # the wizard reached "done"

    @property
    def items(self) -> tuple[tuple[str, bool], ...]:
        return (
            ("account", True),
            ("agent_configured", self.agent_configured),
            ("agent_tested", self.agent_tested),
            ("whatsapp_connected", self.whatsapp_connected),
            ("own_properties", self.own_properties),
        )

    @property
    def done(self) -> int:
        return sum(value for _, value in self.items)


@dataclass(frozen=True, slots=True)
class TenantRow:
    id: UUID
    name: str
    suspended: bool
    plan: str
    trial_ends_at: datetime
    created_at: datetime
    owner_email: str | None
    owner_pending: bool  # created by an admin, the owner has not signed up yet
    onboarding: Onboarding
    whatsapp_status: str | None  # connected | disconnected | error | None
    business_verification: str | None
    leads_last_7_days: int


def whatsapp_badge(status: str | None, verification: str | None) -> WhatsAppBadge:
    if status is None or status == "disconnected":
        return WhatsAppBadge.NOT_CONNECTED
    if status == "error" or verification == "failed":
        return WhatsAppBadge.ACTION_REQUIRED
    if verification == "pending":
        return WhatsAppBadge.VERIFICATION_PENDING
    return WhatsAppBadge.CONNECTED


def needs_help(row: TenantRow, now: datetime) -> bool:
    """WhatsApp in error, onboarding unfinished for more than 48 hours, or a trial ending
    within 3 days without a connected WhatsApp."""
    if row.whatsapp_status == "error":
        return True
    if not row.onboarding.finished and now - row.created_at > ONBOARDING_STUCK_AFTER:
        return True
    return (
        row.plan == "trial"
        and row.trial_ends_at - now <= TRIAL_ENDING_WITHIN
        and row.whatsapp_status != "connected"
    )


def matches(row: TenantRow, wanted: TenantFilter, query: str, now: datetime) -> bool:
    text = query.strip().lower()
    if text and text not in row.name.lower() and text not in (row.owner_email or "").lower():
        return False
    if wanted is TenantFilter.NEEDS_HELP:
        return needs_help(row, now)
    if wanted is TenantFilter.TRIAL:
        return row.plan == "trial"
    return True


@dataclass(frozen=True, slots=True)
class Kpis:
    active: int
    trial: int
    onboarding_unfinished: int
    whatsapp_problems: int


def kpis(rows: Sequence[TenantRow]) -> Kpis:
    live = [row for row in rows if not row.suspended]
    return Kpis(
        active=len(live),
        trial=sum(row.plan == "trial" for row in live),
        onboarding_unfinished=sum(not row.onboarding.finished for row in live),
        whatsapp_problems=sum(
            whatsapp_badge(row.whatsapp_status, row.business_verification)
            is WhatsAppBadge.ACTION_REQUIRED
            for row in live
        ),
    )


def mask(value: str | None) -> str | None:
    """ "•••• 1234": enough for an admin to tell accounts apart."""
    if not value:
        return None
    return f"•••• {value[-4:]}"
