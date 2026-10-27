from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class VerifiedToken:
    user_id: UUID
    email: str


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedToken:
        """Return the authenticated identity or raise InvalidTokenError."""
        ...
