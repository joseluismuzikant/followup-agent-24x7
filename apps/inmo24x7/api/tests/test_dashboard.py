"""The S5 KPIs: each definition with fixed clocks and timezones, then the dashboard over the
database (real leads only) and the endpoint."""

import time as timer
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from followup_core.conversation.domain.thread import Author
from followup_core.tenancy.domain.business_settings import ScheduleBlock
from inbox_fakes import add_lead
from inmo24x7_api.container import _agent_configs, _business_context
from inmo24x7_api.dashboard.application.get_dashboard import GetDashboard
from inmo24x7_api.dashboard.domain.kpis import (
    TranscriptRow,
    average,
    is_out_of_hours,
    is_qualified,
    qualifying_keys,
    response_times,
    week_start,
)
from inmo24x7_api.dashboard.infrastructure.queries import SqlAlchemyDashboardQueries
from inmo24x7_api.leads.domain.lead import LeadStatus, VisitStatus
from inmo24x7_api.leads.infrastructure.repositories import SqlAlchemyLeadRepository
from lead_fakes import DEFAULTS
from test_setup_endpoints import Account

BA = "America/Argentina/Buenos_Aires"
# Thursday 5 November 2026, 15:00 in Buenos Aires.
THURSDAY = datetime(2026, 11, 5, 18, 0, tzinfo=UTC)
WEEK = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)  # Monday 2/11 00:00 in Buenos Aires
NINE_TO_SIX = tuple(ScheduleBlock(day, time(9), time(18)) for day in range(5))


@pytest.fixture
def owner(client: TestClient, auth) -> Account:
    return Account(client, auth)


# --- Definitions ------------------------------------------------------------------------------


def test_the_week_starts_on_monday_at_midnight_in_the_business_timezone() -> None:
    assert week_start(THURSDAY, BA) == WEEK
    # Monday 01:00 UTC is still Sunday 22:00 in Buenos Aires: last week.
    sunday_night = datetime(2026, 11, 9, 1, 0, tzinfo=UTC)
    assert week_start(sunday_night, BA) == WEEK
    assert week_start(sunday_night, "UTC") == datetime(2026, 11, 9, tzinfo=UTC)
    # Monday 03:00 UTC is the new week in Buenos Aires.
    assert week_start(datetime(2026, 11, 9, 3, 0, tzinfo=UTC), BA) == WEEK + timedelta(days=7)


def test_out_of_hours_uses_the_team_schedule_in_its_timezone() -> None:
    # 21:00 UTC is 18:00 in Buenos Aires: closed. 12:00 UTC is 09:00: open.
    assert is_out_of_hours(datetime(2026, 11, 5, 21, 0, tzinfo=UTC), NINE_TO_SIX, BA)
    assert not is_out_of_hours(datetime(2026, 11, 5, 12, 0, tzinfo=UTC), NINE_TO_SIX, BA)
    assert is_out_of_hours(datetime(2026, 11, 7, 15, 0, tzinfo=UTC), NINE_TO_SIX, BA)  # Saturday


def test_qualified_needs_the_enabled_ones_of_operation_zone_and_budget() -> None:
    keys = qualifying_keys(DEFAULTS)
    assert keys == ("operation", "zone", "budget")
    budget = {"amount": 900_000, "currency": "ARS"}

    assert is_qualified({"operation": "alquiler", "zone": "Palermo", "budget": budget}, keys)
    assert not is_qualified({"operation": "alquiler", "zone": "Palermo"}, keys)
    assert is_qualified({"operation": "alquiler", "zone": "Palermo"}, ("operation", "zone"))
    assert not is_qualified({"operation": "alquiler"}, ())


def test_response_time_is_from_the_first_message_of_a_burst_to_the_agents_first_reply() -> None:
    thread, other = uuid4(), uuid4()
    at = WEEK + timedelta(days=1)

    def row(thread_id, author, seconds, sent=None):
        sent_at = at + timedelta(seconds=sent) if sent is not None else None
        return TranscriptRow(thread_id, author, at + timedelta(seconds=seconds), sent_at)

    rows = [
        row(thread, Author.VISITOR, 0),
        row(thread, Author.VISITOR, 2),  # same burst
        row(thread, Author.AGENT, 8, sent=9),  # WhatsApp accepted it at 9 s
        row(thread, Author.AGENT, 9),  # second reply of the same turn: ignored
        row(thread, Author.VISITOR, 100),
        row(thread, Author.HUMAN, 130),  # taken over: the agent never answers this burst
        row(other, Author.VISITOR, 0),
        row(other, Author.AGENT, 3),
        # Before the week started: not counted.
        TranscriptRow(other, Author.VISITOR, WEEK - timedelta(hours=1)),
        TranscriptRow(other, Author.AGENT, WEEK - timedelta(minutes=59)),
    ]

    assert response_times(rows, WEEK) == [9.0, 3.0]
    assert average([9.0, 3.0]) == 6.0
    assert average([]) is None


# --- Over the database -----------------------------------------------------------------------


def _dashboard(db_session, owner: Account, now: datetime = THURSDAY):
    return GetDashboard(
        SqlAlchemyDashboardQueries(db_session),
        SqlAlchemyLeadRepository(db_session),
        _business_context(db_session),
        _agent_configs(db_session),
        clock=lambda: now,
    ).execute(owner.tenant_id)


def test_each_kpi_counts_this_weeks_real_leads(owner: Account, db_session) -> None:
    budget = {"amount": 900_000, "currency": "ARS"}
    full = {"operation": "alquiler", "zone": "Palermo", "budget": budget}
    tenant = owner.tenant_id
    day = WEEK + timedelta(days=1)  # Tuesday 3/11 00:00 in Buenos Aires
    # Tuesday 23:10 in Buenos Aires: out of hours. Answered in 6 s.
    add_lead(
        db_session,
        tenant,
        created_at=day + timedelta(hours=23, minutes=10),
        answers=full,
        status=LeadStatus.VISIT_PROPOSED,
        handed_off_at=day + timedelta(hours=23, minutes=20),
        visits=[(THURSDAY + timedelta(days=2), VisitStatus.PROPOSED)],
        messages=[
            (Author.VISITOR, day + timedelta(hours=23, minutes=10)),
            (Author.AGENT, day + timedelta(hours=23, minutes=10, seconds=6)),
        ],
    )
    # Wednesday 11:00: inside hours, not qualified, a confirmed visit. Answered in 10 s.
    add_lead(
        db_session,
        tenant,
        created_at=day + timedelta(days=1, hours=11),
        answers={"operation": "venta"},
        status=LeadStatus.VISIT_CONFIRMED,
        handed_off_at=day + timedelta(days=1, hours=11, minutes=5),
        visits=[
            (THURSDAY + timedelta(days=3), VisitStatus.CONFIRMED),
            (THURSDAY + timedelta(days=1), VisitStatus.CANCELLED),
        ],
        messages=[
            (Author.VISITOR, day + timedelta(days=1, hours=11)),
            (Author.AGENT, day + timedelta(days=1, hours=11, seconds=10)),
        ],
    )
    # Sunday 22:00 last week (Monday 01:00 UTC): not this week.
    add_lead(
        db_session,
        tenant,
        created_at=WEEK - timedelta(hours=2),
        answers=full,
        visits=[(THURSDAY, VisitStatus.PROPOSED)],
    )
    # A simulator test this week: never counted.
    add_lead(
        db_session,
        tenant,
        created_at=day + timedelta(hours=12),
        answers=full,
        is_test=True,
        status=LeadStatus.VISIT_PROPOSED,
        handed_off_at=day + timedelta(hours=12),
        visits=[(THURSDAY + timedelta(days=1), VisitStatus.PROPOSED)],
        messages=[
            (Author.VISITOR, day + timedelta(hours=12)),
            (Author.AGENT, day + timedelta(hours=13)),
        ],
    )

    dashboard = _dashboard(db_session, owner)

    assert dashboard.week_start == WEEK
    assert (dashboard.received, dashboard.out_of_hours) == (2, 1)
    assert dashboard.qualified == 1
    # Visits created this week: the proposed one and the confirmed one (cancelled excluded).
    assert (dashboard.visits, dashboard.visits_confirmed) == (2, 1)
    assert dashboard.response_seconds == 8.0
    assert [lead.status for lead in dashboard.attention_today] == [
        LeadStatus.VISIT_PROPOSED,
        LeadStatus.QUALIFYING,
    ]


def test_an_empty_week_has_zeros_and_no_response_time(owner: Account, db_session) -> None:
    dashboard = _dashboard(db_session, owner)

    assert (dashboard.received, dashboard.qualified, dashboard.visits) == (0, 0, 0)
    assert dashboard.response_seconds is None
    assert list(dashboard.attention_today) == []


def test_para_atender_hoy_is_five_rows_urgent_first(owner: Account, db_session) -> None:
    now = datetime.now(UTC)
    for index in range(3):
        add_lead(
            db_session,
            owner.tenant_id,
            created_at=now - timedelta(hours=index + 1),
            name=f"Urgente {index}",
            status=LeadStatus.HUMAN_REQUESTED,
            handed_off_at=now - timedelta(hours=index + 1),
        )
    for index in range(4):
        add_lead(
            db_session,
            owner.tenant_id,
            created_at=now - timedelta(minutes=index + 1),
            name=f"Nuevo {index}",
        )

    rows = owner.get("/dashboard").json()["attention_today"]

    assert [row["name"] for row in rows] == [
        "Urgente 2",
        "Urgente 1",
        "Urgente 0",
        "Nuevo 0",
        "Nuevo 1",
    ]


def test_the_endpoint_shape_and_its_speed(owner: Account, db_session) -> None:
    now = datetime.now(UTC)
    for index in range(30):
        add_lead(
            db_session,
            owner.tenant_id,
            created_at=now - timedelta(minutes=index + 1),
            answers={"operation": "alquiler"},
            messages=[
                (Author.VISITOR, now - timedelta(minutes=index + 1)),
                (Author.AGENT, now - timedelta(minutes=index + 1) + timedelta(seconds=4)),
            ],
        )
    owner.get("/dashboard")  # warm up

    started = timer.perf_counter()
    response = owner.get("/dashboard")
    elapsed = timer.perf_counter() - started

    body = response.json()
    assert response.status_code == 200
    assert body["business_name"] == "Inmobiliaria Sur"
    assert body["response_time_seconds"] == pytest.approx(4.0)
    assert body["visits"] == {"total": 0, "confirmed": 0}
    assert len(body["attention_today"]) == 5
    assert elapsed < 0.5  # ~100 ms target; generous for CI machines
