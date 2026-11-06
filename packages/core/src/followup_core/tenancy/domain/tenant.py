import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from .errors import InvalidSuspensionReasonError, InvalidTenantNameError, InvalidTenantSlugError
from .product import FIRST_PRODUCT, Product

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TRIAL_DAYS = 14
MAX_SUSPENSION_REASON = 500


class TenantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Plan(StrEnum):
    TRIAL = "trial"
    PRO = "pro"


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
    plan: Plan = Plan.TRIAL
    # Why an admin suspended it (shown to admins only) and when.
    suspended_reason: str | None = None
    suspended_at: datetime | None = None
    # Which product the business uses; slugs are unique per product.
    product: Product = FIRST_PRODUCT

    @classmethod
    def create(cls, name: str, product: Product = FIRST_PRODUCT) -> "Tenant":
        now = datetime.now(UTC)
        return cls(
            id=uuid4(),
            name=name,
            slug=_slugify(name),
            created_at=now,
            status=TenantStatus.ACTIVE,
            trial_ends_at=now + timedelta(days=_TRIAL_DAYS),
            product=product,
        )

    def rename(self, name: str) -> "Tenant":
        """Change the display name. The slug is a stable identifier and stays as is."""
        return replace(self, name=name)

    @property
    def is_suspended(self) -> bool:
        return self.status is TenantStatus.SUSPENDED

    def suspend(self, reason: str, at: datetime) -> "Tenant":
        """Disables the tenant without deleting anything. Suspending again keeps the first
        date and updates the reason."""
        text = " ".join(reason.split())
        if not text or len(text) > MAX_SUSPENSION_REASON:
            raise InvalidSuspensionReasonError("A suspension needs a reason (1-500 chars).")
        return replace(
            self,
            status=TenantStatus.SUSPENDED,
            suspended_reason=text,
            suspended_at=self.suspended_at if self.is_suspended else at,
        )

    def reactivate(self) -> "Tenant":
        return replace(self, status=TenantStatus.ACTIVE, suspended_reason=None, suspended_at=None)

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()
        if not normalized_name:
            raise InvalidTenantNameError("Tenant name cannot be empty.")
        if not _SLUG_PATTERN.fullmatch(self.slug):
            raise InvalidTenantSlugError("Tenant slug has an invalid format.")

        object.__setattr__(self, "name", normalized_name)
