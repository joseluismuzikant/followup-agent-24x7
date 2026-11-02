"""A listing of the agency. Rules shared by manual edits and spreadsheet imports."""

import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

MAX_TITLE_LENGTH = 120
MAX_ADDRESS_LENGTH = 200
MAX_ZONE_LENGTH = 80
MAX_LINK_LENGTH = 500
MAX_ROOMS = 20
MAX_PRICE = 10_000_000_000


class Operation(StrEnum):
    SALE = "sale"
    RENT = "rent"


class Currency(StrEnum):
    ARS = "ARS"
    USD = "USD"


class PropertyStatus(StrEnum):
    PUBLISHED = "published"
    PAUSED = "paused"


class Problem(StrEnum):
    """Why a property is invalid. Stable codes; the import report words them in Spanish."""

    MISSING_TITLE = "missing_title"
    MISSING_ADDRESS = "missing_address"
    INVALID_OPERATION = "invalid_operation"
    MISSING_ZONE = "missing_zone"
    MISSING_PRICE = "missing_price"
    INVALID_PRICE = "invalid_price"
    INVALID_CURRENCY = "invalid_currency"
    MISSING_ROOMS = "missing_rooms"
    INVALID_ROOMS = "invalid_rooms"
    MISSING_LINK = "missing_link"
    INVALID_LINK = "invalid_link"
    INVALID_STATUS = "invalid_status"
    TOO_LONG = "too_long"


def default_currency(operation: Operation) -> Currency:
    """Sales are quoted in dollars and rents in pesos unless the row says otherwise."""
    return Currency.USD if operation is Operation.SALE else Currency.ARS


_HOST = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)


def is_web_link(value: str) -> bool:
    """An absolute http(s) URL with a real-looking host. Relative paths are not accepted."""
    if not value or any(char.isspace() for char in value):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in {"http", "https"} and bool(_HOST.fullmatch(parts.hostname or ""))


@dataclass(frozen=True, slots=True)
class PropertyFields:
    """Everything a person edits. Text is trimmed by `clean`."""

    title: str
    address: str
    operation: Operation
    zone: str
    price: int
    currency: Currency
    rooms: int
    link: str
    status: PropertyStatus = PropertyStatus.PUBLISHED

    def clean(self) -> "PropertyFields":
        return replace(
            self,
            title=" ".join(self.title.split()),
            address=" ".join(self.address.split()),
            zone=" ".join(self.zone.split()),
            link=self.link.strip(),
        )

    def problems(self) -> list[Problem]:
        """Problems in column order (empty when valid). Expects `clean()`ed fields."""
        found: list[Problem] = []
        for value, missing, limit in (
            (self.title, Problem.MISSING_TITLE, MAX_TITLE_LENGTH),
            (self.address, Problem.MISSING_ADDRESS, MAX_ADDRESS_LENGTH),
            (self.zone, Problem.MISSING_ZONE, MAX_ZONE_LENGTH),
        ):
            if not value:
                found.append(missing)
            elif len(value) > limit:
                found.append(Problem.TOO_LONG)
        if not 0 < self.price <= MAX_PRICE:
            found.append(Problem.INVALID_PRICE)
        if not 1 <= self.rooms <= MAX_ROOMS:
            found.append(Problem.INVALID_ROOMS)
        if not self.link:
            found.append(Problem.MISSING_LINK)
        elif len(self.link) > MAX_LINK_LENGTH or not is_web_link(self.link):
            found.append(Problem.INVALID_LINK)
        return found


@dataclass(frozen=True, slots=True)
class PropertyChanges:
    """A partial edit: only the fields that are set change."""

    title: str | None = None
    address: str | None = None
    operation: Operation | None = None
    zone: str | None = None
    price: int | None = None
    currency: Currency | None = None
    rooms: int | None = None
    link: str | None = None
    status: PropertyStatus | None = None

    def apply(self, fields: PropertyFields) -> PropertyFields:
        changes = {
            name: getattr(self, name)
            for name in PropertyFields.__dataclass_fields__
            if getattr(self, name) is not None
        }
        return replace(fields, **changes)


@dataclass(frozen=True, slots=True)
class Property:
    id: UUID
    tenant_id: UUID
    fields: PropertyFields
    created_at: datetime
    updated_at: datetime

    @property
    def is_published(self) -> bool:
        return self.fields.status is PropertyStatus.PUBLISHED

    def with_fields(self, fields: PropertyFields, now: datetime) -> "Property":
        return replace(self, fields=fields, updated_at=now)
