"""Visit slots: the next half-hour starts inside the team's hours, in the tenant's timezone."""

from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from followup_core.tenancy.domain.business_settings import ScheduleBlock

SLOT_LENGTH = timedelta(minutes=30)
LEAD_TIME = timedelta(hours=2)
SECOND_SLOT_GAP = timedelta(hours=3)
HORIZON_DAYS = 14
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_SHORT_WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def _candidates(
    team_hours: Sequence[ScheduleBlock], timezone: str, now: datetime
) -> Iterator[datetime]:
    """Every half-hour start at least LEAD_TIME after `now` that ends inside a block, in
    order, for the next HORIZON_DAYS days."""
    zone = ZoneInfo(timezone)
    earliest = now.astimezone(zone) + LEAD_TIME
    for offset in range(HORIZON_DAYS + 1):
        day = earliest.date() + timedelta(days=offset)
        blocks = sorted(
            (block for block in team_hours if block.weekday == day.weekday()),
            key=lambda block: block.opens,
        )
        for block in blocks:
            start = datetime.combine(day, block.opens, zone)
            closes = datetime.combine(day, block.closes, zone)
            while start + SLOT_LENGTH <= closes:
                if start >= earliest:
                    yield start
                start += SLOT_LENGTH


def propose_slots(
    team_hours: Sequence[ScheduleBlock],
    timezone: str,
    now: datetime,
) -> list[datetime]:
    """Two real alternatives: the first free slot, and the first one that starts at least
    SECOND_SLOT_GAP later or on another day. Both start at least LEAD_TIME after `now` and
    end inside one of the team's blocks; past times are never proposed. Fewer than two when
    the team has no (or not enough) hours in the next two weeks."""
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware.")
    first: datetime | None = None
    for start in _candidates(team_hours, timezone, now):
        if first is None:
            first = start
        elif start - first >= SECOND_SLOT_GAP or start.date() != first.date():
            return [first, start]
    return [first] if first else []


def slot_label(start: datetime) -> str:
    """ "jueves 6/11, 10:30" in the slot's own timezone."""
    return f"{_WEEKDAYS[start.weekday()]} {start.day}/{start.month}, {start:%H:%M}"


def short_slot_label(start: datetime) -> str:
    """ "jue 6/11 10:30": fits a WhatsApp reply button (20 characters at most)."""
    return f"{_SHORT_WEEKDAYS[start.weekday()]} {start.day}/{start.month} {start:%H:%M}"
