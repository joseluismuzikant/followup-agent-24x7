"""Visit slots: the next half-hour starts inside the team's hours, in the tenant's timezone."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from followup_core.tenancy.domain.business_settings import ScheduleBlock

SLOT_LENGTH = timedelta(minutes=30)
LEAD_TIME = timedelta(hours=2)
HORIZON_DAYS = 14
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def propose_slots(
    team_hours: Sequence[ScheduleBlock],
    timezone: str,
    now: datetime,
    count: int = 2,
) -> list[datetime]:
    """The next `count` slots that start at least LEAD_TIME after `now` and end inside one of
    the team's blocks. Slots start at the block's opening time plus whole half hours; past
    times are never proposed. Empty when the team has no hours in the next two weeks."""
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware.")
    zone = ZoneInfo(timezone)
    earliest = now.astimezone(zone) + LEAD_TIME
    slots: list[datetime] = []
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
                    slots.append(start)
                    if len(slots) == count:
                        return slots
                start += SLOT_LENGTH
    return slots


def slot_label(start: datetime) -> str:
    """ "jueves 6/11, 10:30" in the slot's own timezone."""
    return f"{_WEEKDAYS[start.weekday()]} {start.day}/{start.month}, {start:%H:%M}"
