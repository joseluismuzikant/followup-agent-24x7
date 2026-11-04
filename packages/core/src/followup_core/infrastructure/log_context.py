"""What the current request or job is about: ids only, never personal data.

Log lines, Sentry tags and LLM usage rows read it. The holder is mutable on purpose: FastAPI
runs sync dependencies in a threadpool with a copy of the context, so a ContextVar set there
would never reach the middleware; changing the shared holder does.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, fields
from typing import Any
from uuid import UUID


@dataclass(slots=True)
class LogContext:
    request_id: str | None = None
    tenant_id: str | None = None
    job_id: str | None = None
    job_kind: str | None = None
    channel: str | None = None

    def as_dict(self) -> dict[str, str]:
        """The fields that are set."""
        return {
            field.name: value
            for field in fields(self)
            if (value := getattr(self, field.name)) is not None
        }


_current: ContextVar[LogContext | None] = ContextVar("log_context", default=None)


def current() -> LogContext:
    """The current holder; an empty one (not stored) outside any scope."""
    return _current.get() or LogContext()


def _text(value: UUID | str | None) -> str | None:
    return None if value is None else str(value)


def start(**values: Any) -> Token[LogContext | None]:
    """Opens a fresh holder; `end(token)` closes it. For callers that must keep it open after
    an exception (the HTTP middleware: the error handler runs outside it, in the same task)."""
    return _current.set(LogContext(**{key: _text(value) for key, value in values.items()}))


def end(token: Token[LogContext | None]) -> None:
    _current.reset(token)


@contextmanager
def scope(**values: Any) -> Iterator[LogContext]:
    """A fresh holder for one request or job."""
    token = start(**values)
    try:
        yield current()
    finally:
        end(token)


def bind(**values: Any) -> None:
    """Adds fields to the current scope (no-op outside one)."""
    context = _current.get()
    if context is None:
        return
    for key, value in values.items():
        setattr(context, key, _text(value))
