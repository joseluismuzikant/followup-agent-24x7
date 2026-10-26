import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from .errors import InvalidTenantNameError, InvalidTenantSlugError

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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

    @classmethod
    def create(cls, name: str) -> "Tenant":
        return cls(
            id=uuid4(),
            name=name,
            slug=_slugify(name),
            created_at=datetime.now(UTC),
        )

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise InvalidTenantNameError("Tenant name cannot be empty.")
        if not _SLUG_PATTERN.fullmatch(self.slug):
            raise InvalidTenantSlugError("Tenant slug has an invalid format.")

        object.__setattr__(self, "name", normalized_name)
