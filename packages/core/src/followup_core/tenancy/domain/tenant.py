import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from .errors import InvalidTenantNameError, InvalidTenantSlugError

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TRIAL_DAYS = 14


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


def _slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.strip())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    name: str
    slug: str
    created_at: datetime
    status: TenantStatus
    trial_ends_at: datetime

    @classmethod
    def create(cls, name: str) -> "Tenant":
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            name=name,
            slug=_slugify(name),
            created_at=now,
            status=TenantStatus.ACTIVE,
            trial_ends_at=now + timedelta(days=_TRIAL_DAYS),
        )

    def rename(self, name: str) -> "Tenant":
        """Change the display name. The slug is a stable identifier and stays as is."""
        return replace(self, name=name)

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise InvalidTenantNameError("Tenant name cannot be empty.")
        if not _SLUG_PATTERN.fullmatch(self.slug):
            raise InvalidTenantSlugError("Tenant slug has an invalid format.")

        object.__setattr__(self, "name", normalized_name)
