"""Which days and hours a reminder may go out for one business: never on weekends, never on
an Argentine holiday when "No enviar en feriados" is on, and only inside the send window
(in the business's timezone). A reminder that falls on a day off goes out the next sending
day, never earlier."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from followup_core.tenancy.domain.business_settings import ScheduleBlock

from .policy import SendWindow, WindowPreset

# A business whose window is empty every weekday (team hours only on Saturdays) never
# sends: the search for the next sending day stops after this many days.
MAX_LOOKAHEAD_DAYS = 60


@dataclass(frozen=True, slots=True)
class SendingCalendar:
    timezone: str
    window: SendWindow
    team_hours: Sequence[ScheduleBlock]
    # Non-sending dates (the holidays, when the policy skips them).
    holidays: Collection[date] = frozenset()

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def today(self, now: datetime) -> date:
        return now.astimezone(self.zone).date()

    def ranges(self, day: date) -> list[tuple[time, time]]:
        """The window's hours on that date ([] on a day off)."""
        if day.weekday() >= 5 or day in self.holidays:
            return []
        if self.window.preset is WindowPreset.TEAM:
            return sorted(
                (block.opens, block.closes)
                for block in self.team_hours
                if block.weekday == day.weekday()
            )
        hours = self.window.hours()
        return [hours] if hours else []

    def is_sending_day(self, day: date) -> bool:
        return bool(self.ranges(day))

    def next_sending_day(self, day: date) -> date | None:
        """`day` itself when reminders may go out that day, else the next one."""
        for offset in range(MAX_LOOKAHEAD_DAYS + 1):
            candidate = day + timedelta(days=offset)
            if self.is_sending_day(candidate):
                return candidate
        return None

    def at(self, day: date, moment: time) -> datetime:
        return datetime.combine(day, moment, self.zone)

    def window_start(self, day: date) -> datetime | None:
        ranges = self.ranges(day)
        return self.at(day, ranges[0][0]) if ranges else None

    def send_time(self, day: date, now: datetime) -> datetime | None:
        """When a reminder for `day` goes out: the window's start, or now when the window is
        already open; None when that day's window is over (or it is not a sending day)."""
        for opens, closes in self.ranges(day):
            start, end = self.at(day, opens), self.at(day, closes)
            if now < end:
                return max(start, now)
        return None

    def is_open(self, now: datetime) -> bool:
        local = now.astimezone(self.zone)
        moment = local.time().replace(tzinfo=None)
        return any(opens <= moment < closes for opens, closes in self.ranges(local.date()))
