from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from .errors import IdentityError


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    AGENT = "agent"
    VIEWER = "viewer"


@dataclass(frozen=True, slots=True)
class Profile:
    id: UUID
    email: str
    display_name: str
    tenant_id: UUID
    role: Role
    is_platform_admin: bool

    def __post_init__(self) -> None:
        normalized_email = self.email.strip()
        if not normalized_email:
            raise IdentityError("Profile email cannot be empty.")

        object.__setattr__(self, "email", normalized_email.lower())
