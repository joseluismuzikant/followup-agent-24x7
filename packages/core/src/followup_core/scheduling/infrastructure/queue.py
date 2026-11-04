import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ...infrastructure import log_context
from ..domain.jobs import (
    Job,
    JobError,
    JobHandlers,
    JobStatus,
    NewJob,
    Reschedule,
    RetryLater,
    UnknownJobKindError,
    backoff,
)
from .models import JobModel

logger = logging.getLogger("followup.jobs")

DEFAULT_LEASE = timedelta(minutes=5)

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


class SqlAlchemyJobQueue:
    """Jobs in Postgres, written in the caller's transaction."""

    def __init__(self, session: Session, clock: Clock = utc_now) -> None:
        self._session = session
        self._clock = clock

    def enqueue(self, job: NewJob) -> bool:
        now = self._clock()
        statement = (
            insert(JobModel)
            .values(
                id=uuid4(),
                kind=job.kind,
                payload=dict(job.payload),
                run_at=job.run_at or now,
                status=JobStatus.QUEUED.value,
                attempts=0,
                max_attempts=job.max_attempts,
                dedupe_key=job.dedupe_key,
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(JobModel.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None

    def claim(self, now: datetime, lease: timedelta = DEFAULT_LEASE) -> Job | None:
        """Takes the next due job, or one whose worker died (its lock expired). Two workers
        never get the same job: the row is locked with SKIP LOCKED until this commits."""
        row = self._session.execute(
            text(
                """
                UPDATE jobs SET status = 'running', attempts = attempts + 1,
                       locked_until = :locked_until
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE (status IN ('queued', 'failed') AND run_at <= :now)
                       OR (status = 'running' AND locked_until < :now)
                    ORDER BY run_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, kind, payload, run_at, status, attempts, max_attempts
                """
            ),
            {"now": now, "locked_until": now + lease},
        ).one_or_none()
        if row is None:
            return None
        return Job(
            id=row.id,
            kind=row.kind,
            payload=row.payload,
            run_at=row.run_at,
            status=JobStatus(row.status),
            attempts=row.attempts,
            max_attempts=row.max_attempts,
        )

    def _model(self, job: Job) -> JobModel:
        model = self._session.get(JobModel, job.id)
        if model is None:
            raise LookupError(f"Job {job.id} vanished.")
        return model

    def complete(self, job: Job, now: datetime) -> None:
        model = self._model(job)
        model.status = JobStatus.DONE.value
        model.locked_until = None
        model.finished_at = now

    def reschedule(self, job: Job, run_at: datetime) -> None:
        """Not yet (e.g. a debounce): runs again later without spending an attempt."""
        model = self._model(job)
        model.status = JobStatus.QUEUED.value
        model.run_at = run_at
        model.attempts = max(model.attempts - 1, 0)
        model.locked_until = None

    def fail(self, job: Job, code: str, now: datetime, *, retry: bool, run_at: datetime) -> bool:
        """Records a failed attempt. True when the job is dead (no attempts left)."""
        model = self._model(job)
        model.last_error = code[:120]
        model.locked_until = None
        if not retry or job.attempts >= job.max_attempts:
            model.status = JobStatus.DEAD.value
            model.finished_at = now
            return True
        model.status = JobStatus.FAILED.value
        model.run_at = run_at
        return False


class JobRunner:
    """Claims one job at a time and runs it. Claiming, running and recording the outcome are
    separate transactions, so a slow handler never holds the queue lock. Delivery is
    at-least-once: handlers are idempotent."""

    def __init__(
        self,
        sessions: Callable[[], Session],
        handlers: Callable[[Session], JobHandlers],
        clock: Clock = utc_now,
        lease: timedelta = DEFAULT_LEASE,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._sessions = sessions
        self._handlers = handlers
        self._clock = clock
        self._lease = lease
        self._jitter = jitter

    def run_next(self) -> bool:
        """Runs one due job. False when there was nothing to do."""
        with self._sessions() as session:
            job = SqlAlchemyJobQueue(session, self._clock).claim(self._clock(), self._lease)
            session.commit()
        if job is None:
            return False
        # Log lines (and error reports) of this job carry its id and kind; handlers add the
        # tenant once they know it.
        with log_context.scope(
            job_id=job.id, job_kind=job.kind, tenant_id=job.payload.get("tenant_id")
        ):
            self._run(job)
        return True

    def _run(self, job: Job) -> None:
        try:
            with self._sessions() as session:
                result = self._handlers(session).get(job.kind)(job)
                session.commit()
        except Exception as error:
            self._record_failure(job, error)
            return

        if isinstance(result, RetryLater):
            self._record_failure(job, JobError(result.code))
            return
        with self._sessions() as session:
            queue = SqlAlchemyJobQueue(session, self._clock)
            if isinstance(result, Reschedule):
                queue.reschedule(job, result.run_at)
            else:
                queue.complete(job, self._clock())
            session.commit()

    def run_due(self, limit: int = 1000) -> int:
        """Runs due jobs until none is left (tests and scripts). Returns how many ran."""
        count = 0
        while count < limit and self.run_next():
            count += 1
        return count

    def _record_failure(self, job: Job, error: Exception) -> None:
        if isinstance(error, JobError):
            code, retry = error.code, error.retry
        elif isinstance(error, UnknownJobKindError):
            code, retry = "unknown_job_kind", False
        else:
            code, retry = type(error).__name__, True
        now = self._clock()
        with self._sessions() as session:
            dead = SqlAlchemyJobQueue(session, self._clock).fail(
                job, code, now, retry=retry, run_at=now + backoff(job.attempts, self._jitter)
            )
            session.commit()
        log = logger.error if dead else logger.warning
        log(
            "job_dead" if dead else "job_failed",
            extra={"job_id": str(job.id), "kind": job.kind, "attempt": job.attempts, "code": code},
            exc_info=not isinstance(error, JobError),
        )
