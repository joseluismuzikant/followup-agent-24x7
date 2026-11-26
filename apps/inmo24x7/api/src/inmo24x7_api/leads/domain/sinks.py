"""`LeadSink`: delivers a lead handed off to the team to an external system (Tokko Broker's
web contacts, the agency's webhook). The graph never knows about sinks: the hand-off queues
one delivery job per enabled sink, and adapters can be added without touching it."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ChosenProperty:
    id: UUID
    title: str
    address: str
    operation: str  # sale / rent
    price_label: str
    link: str
    # manual / tokko, and the external system's id and code when it came from one.
    source: str
    external_id: str | None = None
    external_ref: str | None = None


@dataclass(frozen=True, slots=True)
class QualifiedVisit:
    starts_at: datetime
    label: str  # "mié 18/11 09:00"
    property_label: str
    status: str  # proposed / confirmed


@dataclass(frozen=True, slots=True)
class QualifiedLead:
    """A lead as it goes out: what the team would read in the hand-off email."""

    id: UUID
    tenant_id: UUID
    created_at: datetime
    handed_off_at: datetime | None
    hand_off_reason: str | None  # human / visit / qualified / stalled / agent_failure
    name: str | None
    phone: str | None
    email: str | None
    operation: str | None  # sale / rent
    zone: str | None
    rooms: int | None
    budget: Mapping[str, Any] | None  # {"amount", "currency"}
    # The lead's situation as they said it (garantia, plazo_meses, tiene_mascota, ...).
    conditions: Mapping[str, Any]
    chosen: Sequence[ChosenProperty]
    visit: QualifiedVisit | None
    # "Busca alquiler 2 amb. en Palermo, hasta $900.000, garantía: caución. ... — vía inmo24x7"
    summary: str
    panel_link: str
    do_not_contact: bool
    source: str | None  # web_button, or None
    channel: str
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SinkResult:
    status_code: int
    # The external system's id for what it created, when it says (not stored if absent).
    external_id: str | None = None


class LeadSinkError(Exception):
    """A delivery failed: a stable code, the HTTP status if there was one, and whether
    trying again can help (a timeout or a 5xx, yes; a revoked key or a 400, no)."""

    def __init__(self, code: str, *, status_code: int | None = None, retry: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retry = retry


class LeadSink(Protocol):
    def deliver(self, lead: QualifiedLead, delivery_id: UUID, event: str) -> SinkResult: ...
