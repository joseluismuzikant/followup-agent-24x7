"""The job worker loop, shared by every product (`python -m <product>_api.worker`).

WORKER_CONCURRENCY threads each claim one job at a time from the product's queue (SKIP
LOCKED, so they never share one), run it in its own session and transaction, and sleep
briefly when there is nothing to do. SIGTERM or Ctrl+C lets running jobs finish, then exits.
"""

import logging
import signal
import threading
from collections.abc import Callable
from types import FrameType

from followup_core.scheduling.infrastructure.queue import JobRunner

from .settings import ConfigurationError, Settings

IDLE_SECONDS = 0.5

logger = logging.getLogger("followup.worker")


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


def run(
    settings: Settings,
    build_runner: Callable[[], JobRunner],
    schedule_housekeeping: Callable[[], None],
    on_stop: Callable[[], None] = lambda: None,
) -> int:
    """Runs until SIGTERM/SIGINT; `on_stop` runs after the last job (e.g. a LangSmith
    flush)."""
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
    logger.info(
        "worker_started",
        extra={"concurrency": settings.worker_concurrency, "queue": settings.product.value},
    )
    while not stop.is_set():
        stop.wait(1)
    for thread in threads:
        thread.join(timeout=60)
    on_stop()
    logger.info("worker_stopped")
    return 0
