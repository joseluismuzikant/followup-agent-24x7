"""The Postgres job queue against the test database."""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from followup_core.scheduling.domain.jobs import (
    Job,
    JobError,
    JobHandlers,
    NewJob,
    Reschedule,
    backoff,
)
from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def sessions(database) -> sessionmaker[Session]:
    return sessionmaker(bind=database, autoflush=False, expire_on_commit=False)


def _enqueue(sessions, job: NewJob, clock: Clock | None = None) -> bool:
    with sessions() as session:
        added = SqlAlchemyJobQueue(session, clock or Clock()).enqueue(job)
        session.commit()
    return added


def _jobs(sessions) -> list[tuple]:
    with sessions() as session:
        return list(
            session.execute(
                text("SELECT kind, status, attempts, last_error FROM jobs ORDER BY created_at")
            ).all()
        )


def test_two_workers_never_claim_the_same_job(sessions) -> None:
    _enqueue(sessions, NewJob("a"))
    _enqueue(sessions, NewJob("b"))

    with sessions() as first, sessions() as second:
        one = SqlAlchemyJobQueue(first).claim(T0 + timedelta(seconds=1))
        # The first transaction still holds its row lock: the second skips it.
        two = SqlAlchemyJobQueue(second).claim(T0 + timedelta(seconds=1))
        three = SqlAlchemyJobQueue(second).claim(T0 + timedelta(seconds=1))
        first.commit()
        second.commit()

    assert one is not None and two is not None
    assert {one.kind, two.kind} == {"a", "b"}
    assert three is None


def test_jobs_run_when_due_and_finish_done(sessions) -> None:
    clock = Clock()
    ran: list[str] = []
    _enqueue(sessions, NewJob("later", {"n": 1}, run_at=T0 + timedelta(minutes=5)), clock)
    handlers = JobHandlers([("later", lambda job: ran.append(job.payload["n"]))])
    runner = JobRunner(sessions, lambda _session: handlers, clock)

    assert runner.run_next() is False
    clock.now = T0 + timedelta(minutes=5)
    assert runner.run_next() is True

    assert ran == [1]
    assert _jobs(sessions) == [("later", "done", 1, None)]


def test_failures_retry_with_backoff_then_die(sessions, caplog) -> None:
    jobs_logger = logging.getLogger("followup.jobs")
    # Alembic's fileConfig (run by the database fixture) disables existing loggers.
    jobs_logger.disabled = False
    jobs_logger.addHandler(caplog.handler)
    clock = Clock()
    _enqueue(sessions, NewJob("flaky", max_attempts=3), clock)

    def fail(job: Job) -> None:
        raise JobError("meta_unavailable")

    runner = JobRunner(
        sessions, lambda _s: JobHandlers([("flaky", fail)]), clock, jitter=lambda: 0.5
    )
    runner.run_next()
    assert _jobs(sessions) == [("flaky", "failed", 1, "meta_unavailable")]
    # Not due before the backoff (5 s for the first retry).
    clock.now = T0 + timedelta(seconds=4)
    assert runner.run_next() is False
    clock.now = T0 + timedelta(seconds=5)
    assert runner.run_next() is True
    clock.now = T0 + timedelta(minutes=5)
    runner.run_next()

    assert _jobs(sessions) == [("flaky", "dead", 3, "meta_unavailable")]
    assert any(record.getMessage() == "job_dead" for record in caplog.records)
    jobs_logger.removeHandler(caplog.handler)


def test_permanent_errors_and_unknown_kinds_die_at_once(sessions) -> None:
    clock = Clock()
    _enqueue(sessions, NewJob("permanent"), clock)
    _enqueue(sessions, NewJob("nobody_handles_this"), clock)

    def permanent(job: Job) -> None:
        raise JobError("bad_request", retry=False)

    runner = JobRunner(sessions, lambda _s: JobHandlers([("permanent", permanent)]), clock)
    runner.run_due()

    assert sorted(_jobs(sessions)) == [
        ("nobody_handles_this", "dead", 1, "unknown_job_kind"),
        ("permanent", "dead", 1, "bad_request"),
    ]


def test_a_stuck_job_is_reclaimed_after_its_lock_expires(sessions) -> None:
    _enqueue(sessions, NewJob("stuck"))
    with sessions() as session:
        # A worker claimed it and died without finishing.
        assert SqlAlchemyJobQueue(session).claim(T0, lease=timedelta(minutes=5)) is not None
        session.commit()

    with sessions() as session:
        assert SqlAlchemyJobQueue(session).claim(T0 + timedelta(minutes=4)) is None
        again = SqlAlchemyJobQueue(session).claim(T0 + timedelta(minutes=6))
        session.commit()

    assert again is not None and again.attempts == 2


def test_dedupe_keys_drop_the_second_job(sessions) -> None:
    assert _enqueue(sessions, NewJob("email", dedupe_key="lead-email:1:handoff")) is True
    assert _enqueue(sessions, NewJob("email", dedupe_key="lead-email:1:handoff")) is False
    assert _enqueue(sessions, NewJob("email", dedupe_key="lead-email:2:handoff")) is True
    assert len(_jobs(sessions)) == 2


def test_reschedule_runs_later_without_spending_an_attempt(sessions) -> None:
    clock = Clock()
    _enqueue(sessions, NewJob("debounced", max_attempts=1), clock)
    calls: list[datetime] = []

    def handler(job: Job) -> Reschedule | None:
        calls.append(clock.now)
        return Reschedule(T0 + timedelta(seconds=3)) if len(calls) == 1 else None

    runner = JobRunner(sessions, lambda _s: JobHandlers([("debounced", handler)]), clock)
    runner.run_next()
    assert runner.run_next() is False
    clock.now = T0 + timedelta(seconds=3)
    runner.run_next()

    assert _jobs(sessions) == [("debounced", "done", 1, None)]


def test_backoff_grows_and_is_capped() -> None:
    assert backoff(1, lambda: 0.5) == timedelta(seconds=5)
    assert backoff(3, lambda: 0.5) == timedelta(seconds=20)
    assert backoff(30, lambda: 0.5) == timedelta(minutes=30)
    assert backoff(1, lambda: 0.0) == timedelta(seconds=2.5)


def test_each_kind_has_exactly_one_handler() -> None:
    with pytest.raises(ValueError, match="two handlers"):
        JobHandlers([("a", lambda job: None), ("a", lambda job: None)])
