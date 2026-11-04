"""Open issues from Sentry's API for the backoffice's Errores page (read-only token).

Never fails the page: without SENTRY_API_TOKEN / SENTRY_ORG / SENTRY_PROJECTS the result is
"not configured", and a Sentry error or timeout is "unavailable". Answers are cached for a
minute per question, so a busy Salud del sistema does not hammer the API.
"""

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import httpx

logger = logging.getLogger("inmo24x7.backoffice")

Period = Literal["24h", "7d", "14d"]
CACHE_SECONDS = 60
TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class Issue:
    id: str
    title: str
    culprit: str
    area: str  # api (API and worker), panel or backoffice
    first_seen: datetime
    last_seen: datetime
    count: int
    users: int
    permalink: str


@dataclass(frozen=True, slots=True)
class IssueList:
    configured: bool
    available: bool
    issues: Sequence[Issue] = ()


def _issue(area: str, item: Mapping[str, Any]) -> Issue:
    return Issue(
        id=str(item["id"]),
        title=str(item.get("title", "")),
        culprit=str(item.get("culprit") or ""),
        area=area,
        first_seen=datetime.fromisoformat(item["firstSeen"]),
        last_seen=datetime.fromisoformat(item["lastSeen"]),
        count=int(item.get("count") or 0),
        users=int(item.get("userCount") or 0),
        permalink=str(item.get("permalink", "")),
    )


class SentryIssuesClient:
    def __init__(
        self,
        api_url: str,
        token: str,
        org: str,
        projects: Mapping[str, str],
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._token = token
        self._org = org
        self._projects = dict(projects)
        self._transport = transport
        self._clock = clock
        self._cache: dict[tuple[Any, ...], tuple[float, IssueList]] = {}
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self._token and self._org and self._projects)

    @property
    def issues_url(self) -> str:
        """The organization's issue list in Sentry's UI (US and EU orgs alike live at
        <org>.sentry.io); the backoffice appends its own search."""
        return f"https://{self._org}.sentry.io/issues/" if self._org else ""

    def recent(
        self,
        area: str | None = None,
        period: Period = "24h",
        tenant_id: UUID | None = None,
        limit: int = 25,
    ) -> IssueList:
        if not self.configured:
            return IssueList(configured=False, available=False)
        key = (area, period, tenant_id, limit)
        now = self._clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_SECONDS:
                return cached[1]
        result = self._fetch(area, period, tenant_id, limit)
        if result.available:
            with self._lock:
                self._cache[key] = (now, result)
        return result

    def _fetch(
        self, area: str | None, period: Period, tenant_id: UUID | None, limit: int
    ) -> IssueList:
        query = f"is:unresolved lastSeen:-{period}"
        if tenant_id is not None:
            query += f" tenant_id:{tenant_id}"
        areas = [area] if area else list(self._projects)
        issues: list[Issue] = []
        try:
            with httpx.Client(
                base_url=self._api_url,
                headers={"Authorization": f"Bearer {self._token}"},
                timeout=TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                for name in areas:
                    slug = self._projects.get(name)
                    if slug is None:
                        continue
                    response = client.get(
                        f"/api/0/projects/{self._org}/{slug}/issues/",
                        params={"query": query, "limit": limit, "sort": "date"},
                    )
                    response.raise_for_status()
                    issues.extend(_issue(name, item) for item in response.json())
        except (httpx.HTTPError, ValueError, KeyError) as error:
            # The status code says enough; Sentry's body may echo the query.
            status = (
                error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
            )
            logger.warning(
                "sentry_issues_unavailable",
                extra={"error": type(error).__name__, "status_code": status},
            )
            return IssueList(configured=True, available=False)
        issues.sort(key=lambda issue: issue.last_seen, reverse=True)
        return IssueList(configured=True, available=True, issues=issues[:limit])
