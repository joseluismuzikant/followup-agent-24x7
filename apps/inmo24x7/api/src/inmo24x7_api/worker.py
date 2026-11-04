"""The job worker: `python -m inmo24x7_api.worker` (scripts/dev.py starts it next to the API;
in production the API image runs it with this command).

WORKER_CONCURRENCY threads each claim one job at a time (SKIP LOCKED, so they never share
one), run it in its own session and transaction, and sleep briefly when there is nothing to
do. SIGTERM or Ctrl+C lets running jobs finish, then exits.
"""

import logging
import signal
import threading
from datetime import UTC, datetime
from types import FrameType

from followup_core.messaging.application.health import health_sweep_job
from followup_core.messaging.application.pipeline import purge_job
from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue

from .config import ConfigurationError, Settings, get_settings
from .container import (
    get_language_model,
    get_messaging_services,
    get_tracing,
    get_turn_tracing,
    job_handlers,
)
from .database import SessionLocal
from .logging import configure_logging
from .tracing import flush

IDLE_SECONDS = 0.5

logger = logging.getLogger("inmo24x7.worker")


def build_runner() -> JobRunner:
    services = get_messaging_services()
    llm = get_language_model()
    tracing = get_turn_tracing()
    return JobRunner(SessionLocal, lambda session: job_handlers(session, services, llm, tracing))


def schedule_housekeeping() -> None:
    """Recurring jobs (daily purge, 6-hourly WhatsApp health); the dedupe keys make every
    worker start agree on one per period. Each run schedules the next one."""
    now = datetime.now(UTC)
    with SessionLocal() as session:
        queue = SqlAlchemyJobQueue(session)
        queue.enqueue(purge_job(now))
        queue.enqueue(health_sweep_job(now))
        session.commit()


def work(runner: JobRunner, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            if not runner.run_next():
                stop.wait(IDLE_SECONDS)
        except Exception:
            # Claiming or recording failed (e.g. the database restarted): back off a moment.
            logger.exception("worker_loop_error")
            stop.wait(5)


def check_pool(settings: Settings) -> None:
    """Each job thread holds a connection, plus one for claiming and housekeeping."""
    needed = settings.worker_concurrency + 1
    if settings.db_pool_size + settings.db_max_overflow < needed:
        raise ConfigurationError(
            f"The worker needs DB_POOL_SIZE + DB_MAX_OVERFLOW >= WORKER_CONCURRENCY + 1 ({needed})."
        )


def main() -> int:
    configure_logging()
    settings = get_settings()
    check_pool(settings)
    if settings.rehearsal:
        logger.warning("rehearsal_mode", extra={"detail": "Fake model and log sender."})
    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("worker_stopping", extra={"signal": signum})
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    runner = build_runner()
    schedule_housekeeping()
    threads = [
        threading.Thread(target=work, args=(runner, stop), name=f"worker-{n}", daemon=True)
        for n in range(settings.worker_concurrency)
    ]
    for thread in threads:
        thread.start()
    logger.info("worker_started", extra={"concurrency": settings.worker_concurrency})
    while not stop.is_set():
        stop.wait(1)
    for thread in threads:
        thread.join(timeout=60)
    flush(get_tracing())  # send pending LangSmith runs
    logger.info("worker_stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
