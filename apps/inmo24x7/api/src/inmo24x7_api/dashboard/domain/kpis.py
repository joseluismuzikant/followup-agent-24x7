"""The S5 KPIs, defined once ("Esto pasó esta semana con tu agente"). Pure functions: the
queries fetch rows, these decide what counts. Real leads only (never simulator tests)."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from followup_core.conversation.domain.thread import Author
from followup_core.tenancy.domain.agent_config import AgentConfig
from followup_core.tenancy.domain.business_settings import ScheduleBlock, is_within_hours

# "Calificadas · Con zona y presupuesto": the answers that make a lead qualified, among the
# ones the business asks (a disabled question is not required).
QUALIFYING_KEYS = ("operation", "zone", "budget")


def week_start(now: datetime, timezone: str) -> datetime:
    """Monday 00:00 of `now`'s week in the business's timezone (an aware datetime)."""
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday, time(), zone)


def qualifying_keys(config: AgentConfig) -> tuple[str, ...]:
    enabled = {question.key for question in config.qualification_questions if question.enabled}
    return tuple(key for key in QUALIFYING_KEYS if key in enabled)


def is_qualified(answers: Mapping[str, Any], keys: Sequence[str]) -> bool:
    return bool(keys) and all(answers.get(key) not in (None, "") for key in keys)


def is_out_of_hours(at: datetime, team_hours: tuple[ScheduleBlock, ...], timezone: str) -> bool:
    """The lead's first message arrived when the team was not working."""
    return not is_within_hours(team_hours, timezone, at)


@dataclass(frozen=True, slots=True)
class TranscriptRow:
    """One stored message, as the response-time KPI reads it (no text)."""

    thread_id: UUID
    author: Author
    created_at: datetime
    # When WhatsApp accepted an agent reply (its first part), if it was sent there.
    sent_at: datetime | None = None


def response_times(rows: Iterable[TranscriptRow], since: datetime) -> list[float]:
    """Seconds from the first message of each inbound burst since `since` to the agent's
    first reply to it. Rows come ordered by thread and position. A burst starts at a visitor
    message right after a message that was not the visitor's; a burst the agent never
    answered (taken over by the team) does not count."""
    seconds: list[float] = []
    started: datetime | None = None
    thread: UUID | None = None
    previous: Author | None = None
    for row in rows:
        if row.thread_id != thread:
            thread, started, previous = row.thread_id, None, None
        if row.author is Author.VISITOR and previous is not Author.VISITOR:
            started = row.created_at if row.created_at >= since else None
        elif row.author is Author.AGENT and started is not None:
            replied = row.sent_at or row.created_at
            seconds.append(max((replied - started).total_seconds(), 0.0))
            started = None
        previous = row.author
    return seconds


def average(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None
