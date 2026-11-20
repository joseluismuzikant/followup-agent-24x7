"""Per-agency integrations: Tokko Broker, the lead webhook and the website button.

Credentials (Tokko's API key, the webhook secret) are stored encrypted with TokenCipher
and never leave the API: the panel only learns whether they are set. The webhook secret is
shown once, when it is generated, so the agency can configure its receiver."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID


class Provider(StrEnum):
    TOKKO = "tokko"
    WEBHOOK = "webhook"
    WIDGET = "widget"


class SyncStatus(StrEnum):
    QUEUED = "queued"
    OK = "ok"
    FAILED = "failed"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    RETRYING = "retrying"  # failed, tried again with the job queue's backoff
    DELIVERED = "delivered"
    FAILED = "failed"  # gave up: a permanent error or no attempts left


TOKKO_DEFAULTS: Mapping[str, Any] = {"import_properties": True, "send_leads": True}
WIDGET_DEFAULTS: Mapping[str, Any] = {
    "color": "#047857",
    "text_color": "#ffffff",
    "position": "right",
    "label": "Consultar por WhatsApp",
}
DELIVERY_LOG_SIZE = 20


@dataclass(frozen=True, slots=True)
class Integration:
    tenant_id: UUID
    provider: Provider
    enabled: bool
    options: Mapping[str, Any]
    updated_at: datetime
    # Encrypted (TokenCipher): Tokko's API key, the webhook secret.
    credentials: str | None = None
    # The website button's public id (`data-agencia`).
    public_id: str | None = None
    last_sync_at: datetime | None = None
    last_sync_status: SyncStatus | None = None
    last_delivery_at: datetime | None = None
    last_delivery_status: DeliveryStatus | None = None
    last_error_code: str | None = None

    def option(self, name: str) -> Any:
        defaults = TOKKO_DEFAULTS if self.provider is Provider.TOKKO else WIDGET_DEFAULTS
        return self.options.get(name, defaults.get(name))

    def with_options(self, at: datetime, **values: Any) -> "Integration":
        return replace(self, options={**self.options, **values}, updated_at=at)


@dataclass(frozen=True, slots=True)
class SyncFailure:
    external_id: str
    title: str
    reason: str


@dataclass(frozen=True, slots=True)
class SyncReport:
    id: UUID
    tenant_id: UUID
    provider: Provider
    started_at: datetime
    finished_at: datetime
    created: int = 0
    updated: int = 0
    paused: int = 0
    unchanged: int = 0
    failed: Sequence[SyncFailure] = field(default_factory=tuple)
    # The whole sync failed (tokko_key_invalid, tokko_unavailable, ...).
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class LeadDelivery:
    id: UUID  # also the X-Inmo24x7-Delivery header, the same on every retry
    tenant_id: UUID
    provider: Provider
    event: str
    status: DeliveryStatus
    created_at: datetime
    updated_at: datetime
    lead_id: UUID | None = None  # None for "Enviar prueba"
    attempts: int = 0
    status_code: int | None = None
    error_code: str | None = None
    delivered_at: datetime | None = None


class IntegrationRepository(Protocol):
    def get(self, tenant_id: UUID, provider: Provider) -> Integration | None: ...

    def save(self, item: Integration) -> None: ...

    def enabled(self, provider: Provider) -> Sequence[Integration]: ...

    def by_public_id(self, public_id: str) -> Integration | None: ...


class SyncReportRepository(Protocol):
    def add(self, report: SyncReport) -> None: ...

    def last(self, tenant_id: UUID, provider: Provider) -> SyncReport | None: ...


class DeliveryRepository(Protocol):
    def add(self, delivery: LeadDelivery) -> None: ...

    def get(self, delivery_id: UUID) -> LeadDelivery | None: ...

    def save(self, delivery: LeadDelivery) -> None: ...

    def recent(
        self, tenant_id: UUID, provider: Provider, limit: int = DELIVERY_LOG_SIZE
    ) -> Sequence[LeadDelivery]: ...

    def for_lead(self, tenant_id: UUID, lead_id: UUID) -> Sequence[LeadDelivery]: ...


class IntegrationError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
