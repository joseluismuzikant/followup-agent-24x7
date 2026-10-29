import re
from dataclasses import dataclass, replace
from datetime import datetime, time
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .errors import (
    InvalidBusinessTypeError,
    InvalidNotificationEmailError,
    InvalidTeamHoursError,
)

DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires"
MAX_NOTIFICATION_EMAILS = 5
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class BusinessType(StrEnum):
    AGENCY = "inmobiliaria"
    NETWORK = "red_franquicia"
    BROKER = "corredor"
    DEVELOPER = "desarrolladora"

    @classmethod
    def parse(cls, value: str) -> "BusinessType":
        try:
            return cls(value)
        except ValueError as error:
            raise InvalidBusinessTypeError(f"Unknown business type '{value}'.") from error


@dataclass(frozen=True, slots=True)
class ScheduleBlock:
    """Opening hours for one weekday (Monday is 0)."""

    weekday: int
    opens: time
    closes: time


def _hours(weekdays: range, opens: time, closes: time) -> tuple[ScheduleBlock, ...]:
    return tuple(ScheduleBlock(day, opens, closes) for day in weekdays)


# Presets offered by the UI. They are plain schedules, not a separate concept.
TEAM_HOURS_WEEKDAYS_9_18 = _hours(range(0, 5), time(9), time(18))
TEAM_HOURS_MON_SAT_9_13 = _hours(range(0, 6), time(9), time(13))


def validate_team_hours(blocks: tuple[ScheduleBlock, ...]) -> tuple[ScheduleBlock, ...]:
    for block in blocks:
        if not 0 <= block.weekday <= 6:
            raise InvalidTeamHoursError("Weekday must be between 0 and 6.")
        if block.opens >= block.closes:
            raise InvalidTeamHoursError("Opening time must be before closing time.")

    ordered = tuple(sorted(blocks, key=lambda block: (block.weekday, block.opens)))
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if previous.weekday == current.weekday and current.opens < previous.closes:
            raise InvalidTeamHoursError("Schedule blocks cannot overlap.")
    return ordered


def validate_notification_emails(emails: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for email in emails:
        value = email.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(value):
            raise InvalidNotificationEmailError(f"'{email}' is not a valid email.")
        if value not in normalized:
            normalized.append(value)
    if not 1 <= len(normalized) <= MAX_NOTIFICATION_EMAILS:
        raise InvalidNotificationEmailError(
            f"Provide between 1 and {MAX_NOTIFICATION_EMAILS} notification emails."
        )
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class BusinessSettings:
    tenant_id: UUID
    business_type: BusinessType
    timezone: str
    team_hours: tuple[ScheduleBlock, ...]
    notification_emails: tuple[str, ...]

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise InvalidTeamHoursError(f"Unknown timezone '{self.timezone}'.") from error
        object.__setattr__(self, "team_hours", validate_team_hours(tuple(self.team_hours)))
        object.__setattr__(
            self,
            "notification_emails",
            validate_notification_emails(tuple(self.notification_emails)),
        )

    def with_changes(
        self,
        *,
        business_type: BusinessType | None = None,
        team_hours: tuple[ScheduleBlock, ...] | None = None,
        notification_emails: tuple[str, ...] | None = None,
    ) -> "BusinessSettings":
        return replace(
            self,
            business_type=business_type or self.business_type,
            team_hours=self.team_hours if team_hours is None else team_hours,
            notification_emails=(
                self.notification_emails if notification_emails is None else notification_emails
            ),
        )


def is_within_team_hours(settings: BusinessSettings, at: datetime) -> bool:
    """True when `at` falls inside the team's schedule in the tenant's timezone."""
    if at.tzinfo is None:
        raise ValueError("`at` must be timezone-aware.")
    local = at.astimezone(ZoneInfo(settings.timezone))
    local_time = local.time().replace(tzinfo=None)
    return any(
        block.weekday == local.weekday() and block.opens <= local_time < block.closes
        for block in settings.team_hours
    )
