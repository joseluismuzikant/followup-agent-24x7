"""Jobs: work that must survive a restart and must not run inside a request."""

import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

BASE_BACKOFF = timedelta(seconds=5)
MAX_BACKOFF = timedelta(minutes=30)
DEFAULT_MAX_ATTEMPTS = 8


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"  # the last attempt failed; it runs again at run_at
    DEAD = "dead"  # gave up after max_attempts


@dataclass(frozen=True, slots=True)
class Job:
    id: UUID
    kind: str
    payload: Mapping[str, Any]
    run_at: datetime
    status: JobStatus
    attempts: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class Reschedule:
    """A handler's way to say "not yet": runs again at `run_at` without using an attempt."""

    run_at: datetime


@dataclass(frozen=True, slots=True)
class RetryLater:
    """A partial success: keep what the handler did (e.g. the messages already sent) and
    retry the rest with backoff. Spends an attempt, like a failure."""

    code: str


class JobError(Exception):
    """A handler failure with a stable code (stored as last_error, never the message text)."""

    def __init__(self, code: str, *, retry: bool = True) -> None:
        super().__init__(code)
        self.code = code
        self.retry = retry


def backoff(attempts: int, jitter: Callable[[], float] = random.random) -> timedelta:
    """Exponential backoff with jitter: base·2^(attempts-1), capped, times 0.5–1.5."""
    delay = min(BASE_BACKOFF * (2 ** max(attempts - 1, 0)), MAX_BACKOFF)
    return delay * (0.5 + jitter())


@dataclass(frozen=True, slots=True)
class NewJob:
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    run_at: datetime | None = None  # None: as soon as possible
    # Unique: a second job with the same key is dropped (one email per lead and kind, ...).
    dedupe_key: str | None = None
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


class JobQueue(Protocol):
    def enqueue(self, job: NewJob) -> bool:
        """Adds the job in the caller's transaction. False when the dedupe key exists."""
        ...


JobHandler = Callable[[Job], Reschedule | RetryLater | None]


class UnknownJobKindError(LookupError):
    pass


class JobHandlers:
    """Each job kind has exactly one handler."""

    def __init__(self, handlers: Iterable[tuple[str, JobHandler]]) -> None:
        self._handlers: dict[str, JobHandler] = {}
        for kind, handler in handlers:
            if kind in self._handlers:
                raise ValueError(f"Job kind '{kind}' has two handlers.")
            self._handlers[kind] = handler

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def get(self, kind: str) -> JobHandler:
        try:
            return self._handlers[kind]
        except KeyError as error:
            raise UnknownJobKindError(kind) from error
