import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .errors import InvalidTenantNameError, InvalidTenantSlugError

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    name: str
    slug: str
    created_at: datetime

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise InvalidTenantNameError("Tenant name cannot be empty.")
        if not _SLUG_PATTERN.fullmatch(self.slug):
            raise InvalidTenantSlugError("Tenant slug has an invalid format.")

        object.__setattr__(self, "name", normalized_name)
