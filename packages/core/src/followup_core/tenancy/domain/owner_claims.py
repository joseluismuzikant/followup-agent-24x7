"""A business created by an admin waits for its owner: the first sign-up with that email
joins it as owner instead of creating a new business."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OwnerClaim:
    email: str
    tenant_id: UUID
    created_at: datetime
    claimed_at: datetime | None = None


class OwnerClaimRepository(Protocol):
    def get_open(self, email: str) -> OwnerClaim | None:
        """The unclaimed claim for this (lowercased) email."""
        ...

    def exists(self, email: str) -> bool: ...

    def add(self, claim: OwnerClaim) -> None: ...

    def mark_claimed(self, email: str, at: datetime) -> None: ...
