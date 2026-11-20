"""`PropertySource`: an agency's listings in an external system (Tokko Broker today).

An adapter turns each external property into one `ExternalListing` per operation (a Tokko
property for sale and for rent is two listings here: the agent searches by operation, and
price and currency belong to the operation), or a `ListingFailure` with the reason in
Spanish. What the source no longer lists is paused here by the sync, never deleted.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from .property import PropertyFields, PropertyOrigin


@dataclass(frozen=True, slots=True)
class ExternalListing:
    external_id: str
    # The agency's own code (Tokko's reference code), if any.
    external_ref: str | None
    # Everything but the conditions, which stay ours.
    fields: PropertyFields


@dataclass(frozen=True, slots=True)
class ListingFailure:
    external_id: str
    title: str
    reason: str  # "no tiene precio publicado."


class PropertySourceError(Exception):
    """The source could not be read at all (a stable code: tokko_key_invalid, ...)."""

    def __init__(self, code: str, *, retry: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retry = retry


class PropertySource(Protocol):
    origin: PropertyOrigin

    def listings(self) -> Iterator[ExternalListing | ListingFailure]:
        """Every published listing. Raises PropertySourceError when it cannot be read."""
        ...
