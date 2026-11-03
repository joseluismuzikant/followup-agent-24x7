from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class SenderKind(StrEnum):
    CLOUD = "cloud"  # the real Cloud API
    LOG = "log"  # local development: nothing leaves the machine


@dataclass(frozen=True, slots=True)
class WhatsAppConnection:
    """One WhatsApp number per tenant. The access token is stored encrypted and is never
    returned by an endpoint or logged."""

    id: UUID
    tenant_id: UUID
    phone_number_id: str
    waba_id: str
    access_token_encrypted: str
    sender: SenderKind
    template_name: str
    template_language: str
    status: ConnectionStatus
    updated_at: datetime
    display_phone_number: str | None = None
    verified_name: str | None = None
    last_error_code: str | None = None
    last_inbound_at: datetime | None = None
    connected_at: datetime | None = None

    @property
    def is_connected(self) -> bool:
        return self.status is ConnectionStatus.CONNECTED

    def with_error(self, code: str, at: datetime) -> "WhatsAppConnection":
        return replace(self, status=ConnectionStatus.ERROR, last_error_code=code, updated_at=at)
