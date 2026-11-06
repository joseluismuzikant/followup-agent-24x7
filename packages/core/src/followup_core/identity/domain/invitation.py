"""An invitation to own a business an admin created ("Dar de alta"): a link with a one-time
token, emailed to the owner. Only the token's hash is stored."""

import hashlib
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from followup_core.tenancy.domain.product import Product

INVITATION_TTL = timedelta(days=7)


class InvitationStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    USED = "used"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Invitation:
    id: UUID
    product: Product
    email: str
    tenant_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    # A newer invitation for the same email and product replaces this one.
    revoked_at: datetime | None = None

    @classmethod
    def create(
        cls, product: Product, email: str, tenant_id: UUID, token: str, now: datetime
    ) -> "Invitation":
        return cls(
            id=uuid4(),
            product=product,
            email=email.strip().lower(),
            tenant_id=tenant_id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=now + INVITATION_TTL,
        )

    def status(self, now: datetime) -> InvitationStatus:
        if self.accepted_at is not None:
            return InvitationStatus.USED
        if self.revoked_at is not None or now >= self.expires_at:
            return InvitationStatus.EXPIRED
        return InvitationStatus.VALID

    def accept(self, now: datetime) -> "Invitation":
        return replace(self, accepted_at=now)


class InvitationRepository(Protocol):
    def get_by_token(self, token: str) -> Invitation | None: ...

    def latest_for(self, product: Product, email: str) -> Invitation | None: ...

    def add(self, invitation: Invitation) -> None:
        """Revokes the open invitations for the same product and email first."""
        ...

    def mark_accepted(self, invitation_id: UUID, at: datetime) -> None: ...
