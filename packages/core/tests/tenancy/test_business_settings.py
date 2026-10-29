from datetime import UTC, datetime, time
from uuid import uuid4

import pytest
from followup_core.tenancy.domain.business_settings import (
    TEAM_HOURS_MON_SAT_9_13,
    TEAM_HOURS_WEEKDAYS_9_18,
    BusinessType,
    ScheduleBlock,
    is_within_team_hours,
)
from followup_core.tenancy.domain.errors import (
    InvalidBusinessTypeError,
    InvalidNotificationEmailError,
    InvalidTeamHoursError,
)
from tenancy_fakes import sample_settings


def _buenos_aires(day: int, hour: int, minute: int = 0) -> datetime:
    # October 2026: the 26th is a Monday. Buenos Aires is UTC-3 with no DST.
    return datetime(2026, 10, day, hour + 3, minute, tzinfo=UTC)


@pytest.mark.parametrize(
    ("at", "expected"),
    [
        (_buenos_aires(26, 9), True),
        (_buenos_aires(26, 17, 59), True),
        (_buenos_aires(26, 18), False),
        (_buenos_aires(26, 8, 59), False),
        (_buenos_aires(31, 10), False),
        (_buenos_aires(30, 12), True),
    ],
)
def test_weekday_preset(at: datetime, expected: bool) -> None:
    settings = sample_settings(uuid4(), team_hours=TEAM_HOURS_WEEKDAYS_9_18)

    assert is_within_team_hours(settings, at) is expected


def test_saturday_preset_closes_at_one() -> None:
    settings = sample_settings(uuid4(), team_hours=TEAM_HOURS_MON_SAT_9_13)

    assert is_within_team_hours(settings, _buenos_aires(31, 12, 59))
    assert not is_within_team_hours(settings, _buenos_aires(31, 13))
    assert not is_within_team_hours(settings, _buenos_aires(25, 10))  # Sunday


def test_uses_the_tenant_timezone_not_utc() -> None:
    settings = sample_settings(uuid4(), team_hours=TEAM_HOURS_WEEKDAYS_9_18)

    # 08:00 UTC on a Monday is 05:00 in Buenos Aires.
    assert not is_within_team_hours(settings, datetime(2026, 10, 26, 8, tzinfo=UTC))
    madrid = sample_settings(uuid4(), timezone="Europe/Madrid", team_hours=TEAM_HOURS_WEEKDAYS_9_18)
    assert is_within_team_hours(madrid, datetime(2026, 10, 26, 8, tzinfo=UTC))


def test_empty_schedule_is_never_within_hours() -> None:
    assert not is_within_team_hours(sample_settings(uuid4(), team_hours=()), _buenos_aires(26, 10))


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        is_within_team_hours(sample_settings(uuid4()), datetime(2026, 10, 26, 10))


@pytest.mark.parametrize(
    "blocks",
    [
        (ScheduleBlock(7, time(9), time(18)),),
        (ScheduleBlock(0, time(18), time(9)),),
        (ScheduleBlock(0, time(9), time(9)),),
        (ScheduleBlock(0, time(9), time(13)), ScheduleBlock(0, time(12), time(18))),
    ],
)
def test_invalid_schedules_are_rejected(blocks) -> None:
    with pytest.raises(InvalidTeamHoursError):
        sample_settings(uuid4(), team_hours=blocks)


def test_split_shifts_are_allowed() -> None:
    settings = sample_settings(
        uuid4(),
        team_hours=(ScheduleBlock(0, time(9), time(13)), ScheduleBlock(0, time(15), time(19))),
    )

    assert is_within_team_hours(settings, _buenos_aires(26, 16))
    assert not is_within_team_hours(settings, _buenos_aires(26, 14))


def test_emails_are_normalized_deduplicated_and_limited() -> None:
    settings = sample_settings(uuid4(), notification_emails=(" A@x.com ", "a@x.com", "b@x.com"))
    assert settings.notification_emails == ("a@x.com", "b@x.com")

    with pytest.raises(InvalidNotificationEmailError):
        sample_settings(uuid4(), notification_emails=())
    with pytest.raises(InvalidNotificationEmailError):
        sample_settings(uuid4(), notification_emails=("not-an-email",))
    with pytest.raises(InvalidNotificationEmailError):
        sample_settings(uuid4(), notification_emails=tuple(f"u{i}@x.com" for i in range(6)))


def test_unknown_timezone_and_business_type_are_rejected() -> None:
    with pytest.raises(InvalidTeamHoursError):
        sample_settings(uuid4(), timezone="Mars/Olympus")
    with pytest.raises(InvalidBusinessTypeError):
        BusinessType.parse("pizzeria")
