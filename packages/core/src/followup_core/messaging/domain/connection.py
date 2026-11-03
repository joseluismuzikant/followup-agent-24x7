from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ConnectionStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class BusinessVerification(StrEnum):
    VERIFIED = "verified"
    PENDING = "pending"
    FAILED = "failed"
    UNKNOWN = "unknown"  # Meta does not tell us (the panel shows neutral copy and links)


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
    # The approved template that confirms a visit outside the 24-hour window (README:
    # "confirmacion_visita"). None until the agency has one.
    visit_template_name: str | None = None
    visit_template_language: str = "es_AR"
    business_id: str | None = None
    quality_rating: str | None = None  # GREEN | YELLOW | RED | NA | UNKNOWN
    name_status: str | None = None  # display name review: APPROVED | PENDING_REVIEW | ...
    business_verification: BusinessVerification = BusinessVerification.UNKNOWN
    # When messages stopped going out (the first failure of the current error).
    failing_since: datetime | None = None
    last_health_check_at: datetime | None = None

    @property
    def is_connected(self) -> bool:
        return self.status is ConnectionStatus.CONNECTED

    @property
    def is_failing(self) -> bool:
        return self.status is ConnectionStatus.ERROR

    def with_error(self, code: str, at: datetime) -> "WhatsAppConnection":
        """A Graph call failed: keep Meta's code. `failing_since` keeps the first failure."""
        return replace(
            self,
            status=ConnectionStatus.ERROR,
            last_error_code=code,
            failing_since=self.failing_since or at,
            updated_at=at,
        )

    def recovered(self, at: datetime) -> "WhatsAppConnection":
        return replace(
            self,
            status=ConnectionStatus.CONNECTED,
            last_error_code=None,
            failing_since=None,
            updated_at=at,
        )
