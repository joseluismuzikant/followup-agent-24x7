from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from followup_core.tenancy.domain.product import FIRST_PRODUCT, Product

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
    # The Supabase user (one per person) and the product: a person has one profile per
    # product. Until a second product, the profile id was the user id; it still is for a
    # user's first profile.
    user_id: UUID | None = None
    product: Product = FIRST_PRODUCT

    def __post_init__(self) -> None:
        if self.user_id is None:
            object.__setattr__(self, "user_id", self.id)
        normalized_email = self.email.strip()
        if not normalized_email:
            raise IdentityError("Profile email cannot be empty.")

        object.__setattr__(self, "email", normalized_email.lower())
