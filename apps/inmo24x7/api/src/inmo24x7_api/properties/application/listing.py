"""Reads a listing into a draft: from its link, from its pasted text, or again for an existing
property ("Actualizar desde el link"). Nothing is saved; the panel's form does that."""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from followup_core.conversation.application.threads import Clock, utc_now
from followup_core.conversation.domain.errors import LlmUnavailableError
from followup_core.conversation.domain.llm import TokenUsage
from followup_core.conversation.domain.usage import LlmCall, LlmOperation, LlmUsageRecorder
from followup_core.tenancy.domain.audit import (
    ActorKind,
    AuditEvent,
    AuditLog,
    NoAuditLog,
)

from ...audit import InmoAction
from ..domain.errors import PropertyManagedExternallyError, PropertyNotFoundError
from ..domain.listing import (
    LINK_READS_PER_HOUR,
    MAX_PAGE_TEXT,
    MAX_PASTED_TEXT,
    MIN_PASTED_TEXT,
    FieldSource,
    LinkReadLimitError,
    ListingDraft,
    ListingFetchError,
    ListingModel,
    ListingTextError,
    ListingUrlError,
    PageFetcher,
    ReadProblem,
    clean_link,
)
from ..domain.property import MAX_LINK_LENGTH, Property, PropertyStatus, is_web_link
from ..domain.repositories import PropertyRepository
from .listing_page import (
    Mapped,
    build_draft,
    map_values,
    missing,
    read_page,
    strip_chrome,
    structured_values,
)

logger = logging.getLogger("inmo24x7.listing")

ReadsSince = Callable[[UUID, datetime], int]
"""Page reads (and pasted texts) of a tenant since a moment: the rate limit's count."""

MODEL_UNAVAILABLE_WARNING = (
    "No pudimos completar los datos con IA ahora. Completá lo que falta a mano."
)
SOLD_WARNING = "La publicación figura como vendida, alquilada o reservada: la dejamos pausada."


@dataclass(frozen=True, slots=True)
class ListingResult:
    draft: ListingDraft
    # The agency already has a property with this link: the panel offers to open it.
    duplicate: Property | None = None


@dataclass(frozen=True, slots=True)
class FieldChange:
    field: str
    current: Any
    read: Any


@dataclass(frozen=True, slots=True)
class RefreshResult:
    draft: ListingDraft
    changes: tuple[FieldChange, ...]


_COMPARED = ("title", "address", "operation", "zone", "price", "currency", "rooms", "status")


def link_for(url: str) -> str:
    """The pasted URL as it is stored. Raises ListingUrlError when it is not a web link."""
    link = clean_link(url)
    if len(link) > MAX_LINK_LENGTH or not is_web_link(link):
        raise ListingUrlError("invalid")
    return link


class ReadListing:
    def __init__(
        self,
        properties: PropertyRepository,
        fetcher: PageFetcher,
        model: ListingModel,
        reads_since: ReadsSince,
        usage: LlmUsageRecorder | None = None,
        audit: AuditLog | None = None,
        clock: Clock = utc_now,
        limit_per_hour: int = LINK_READS_PER_HOUR,
    ) -> None:
        self._properties = properties
        self._fetcher = fetcher
        self._model = model
        self._reads_since = reads_since
        self._usage = usage
        self._audit = audit or NoAuditLog()
        self._clock = clock
        self._limit = limit_per_hour

    # The three entry points.

    def from_link(self, tenant_id: UUID, profile_id: UUID | None, url: str) -> ListingResult:
        link = link_for(url)
        duplicate = self._duplicate(tenant_id, url, link)
        if duplicate is not None:
            return ListingResult(ListingDraft(link=link), duplicate)
        return ListingResult(self._read_link(tenant_id, profile_id, link))

    def from_text(
        self, tenant_id: UUID, profile_id: UUID | None, text: str, url: str
    ) -> ListingResult:
        link = link_for(url)
        cleaned = _pasted(text)
        duplicate = self._duplicate(tenant_id, url, link)
        if duplicate is not None:
            return ListingResult(ListingDraft(link=link), duplicate)
        return ListingResult(self._read_text(tenant_id, profile_id, link, cleaned))

    def refresh(
        self,
        tenant_id: UUID,
        profile_id: UUID | None,
        property_id: UUID,
        text: str | None = None,
    ) -> RefreshResult:
        current = self._properties.get(tenant_id, property_id)
        if current is None:
            raise PropertyNotFoundError(str(property_id))
        if current.is_external:
            raise PropertyManagedExternallyError(str(property_id))
        link = current.fields.link
        if text is not None:
            draft = self._read_text(tenant_id, profile_id, link, _pasted(text))
        else:
            draft = self._read_link(tenant_id, profile_id, link)
        if draft.problem is ReadProblem.GONE:
            draft = replace(draft, status=PropertyStatus.PAUSED)
        return RefreshResult(draft, _changes(current, draft))

    # Reading.

    def _duplicate(self, tenant_id: UUID, url: str, link: str) -> Property | None:
        for candidate in dict.fromkeys((link, url.strip())):
            found = self._properties.get_by_link(tenant_id, candidate)
            if found is not None:
                return found
        return None

    def _allow(self, tenant_id: UUID) -> None:
        since = self._clock() - timedelta(hours=1)
        if self._reads_since(tenant_id, since) >= self._limit:
            raise LinkReadLimitError(str(tenant_id))

    def _read_link(self, tenant_id: UUID, profile_id: UUID | None, link: str) -> ListingDraft:
        self._allow(tenant_id)
        try:
            page = self._fetcher.fetch(link)
        except ListingFetchError as error:
            self._record(tenant_id, profile_id, error.problem.value, "none")
            return ListingDraft(link=link, problem=error.problem)
        parsed = read_page(page.url, page.html)
        structured = map_values(structured_values(parsed))
        warnings: list[str] = []
        model: Mapped | None = None
        if missing(structured.fields) and parsed.text:
            model = self._ask_model(tenant_id, parsed.text[:MAX_PAGE_TEXT], warnings)
        draft = self._finish(build_draft(link, structured, model, tuple(warnings)))
        if not _looks_like_listing(draft):
            draft = replace(draft, problem=ReadProblem.NOT_LISTING)
        self._record(tenant_id, profile_id, str(draft.problem or "read"), _source(draft))
        return draft

    def _read_text(
        self, tenant_id: UUID, profile_id: UUID | None, link: str, text: str
    ) -> ListingDraft:
        self._allow(tenant_id)
        warnings: list[str] = []
        model = self._ask_model(tenant_id, text, warnings)
        draft = self._finish(build_draft(link, Mapped({}, {}), model, tuple(warnings)))
        if model is not None and not _looks_like_listing(draft):
            draft = replace(draft, problem=ReadProblem.NOT_LISTING)
        self._record(tenant_id, profile_id, "text", _source(draft))
        return draft

    def _finish(self, draft: ListingDraft) -> ListingDraft:
        if draft.status is PropertyStatus.PAUSED:
            return replace(draft, warnings=(*draft.warnings, SOLD_WARNING))
        return draft

    def _ask_model(self, tenant_id: UUID, text: str, warnings: list[str]) -> Mapped | None:
        started = time.perf_counter()
        succeeded = False
        usage = None
        try:
            reading = self._model.read(text)
            usage = reading.usage
            succeeded = True
            return map_values(reading.values)
        except LlmUnavailableError as error:
            logger.warning("listing_model_failed", extra={"error": str(error)})
            warnings.append(MODEL_UNAVAILABLE_WARNING)
            return None
        finally:
            self._record_usage(tenant_id, usage, started, succeeded)

    def _record_usage(
        self, tenant_id: UUID, usage: TokenUsage | None, started: float, succeeded: bool
    ) -> None:
        if self._usage is None:
            return
        self._usage.record(
            LlmCall(
                tenant_id=tenant_id,
                thread_id=None,
                channel="panel",
                is_test=False,
                operation=LlmOperation.READ_LISTING,
                model=self._model.model_name,
                usage=usage or TokenUsage(),
                latency_ms=round((time.perf_counter() - started) * 1000),
                succeeded=succeeded,
                created_at=self._clock(),
            )
        )

    def _record(self, tenant_id: UUID, profile_id: UUID | None, code: str, source: str) -> None:
        self._audit.record(
            AuditEvent(
                tenant_id,
                self._clock(),
                ActorKind.USER,
                InmoAction.PROPERTY_LINK_READ,
                {"code": code, "source": source},
                actor_profile_id=profile_id,
            )
        )


def _pasted(text: str) -> str:
    cleaned = strip_chrome(text or "")
    if len(cleaned) < MIN_PASTED_TEXT:
        raise ListingTextError("too_short")
    return cleaned[:MAX_PASTED_TEXT]


def _looks_like_listing(draft: ListingDraft) -> bool:
    """A property says at least two of: a price, rooms, an operation, an address."""
    said = [draft.price, draft.rooms, draft.operation, draft.address or None]
    return sum(value is not None for value in said) >= 2


def _source(draft: ListingDraft) -> str:
    sources = set(draft.sources.values())
    if not sources:
        return "none"
    if sources == {FieldSource.STRUCTURED}:
        return "structured"
    return "model" if sources == {FieldSource.MODEL} else "both"


def _changes(current: Property, draft: ListingDraft) -> tuple[FieldChange, ...]:
    """What the page says differently, among what it says (an empty value is no change)."""
    fields = current.fields
    found: list[FieldChange] = []
    for name in _COMPARED:
        read = getattr(draft, name)
        if read in (None, ""):
            continue
        now = getattr(fields, name)
        if read != now:
            found.append(FieldChange(name, now, read))
    return tuple(found)
