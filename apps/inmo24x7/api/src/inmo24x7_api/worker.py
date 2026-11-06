"""inmo24x7's job worker: `python -m inmo24x7_api.worker` (scripts/dev.py starts it next to
the API; in production the API image runs it with this command). The loop itself is
followup_platform.worker; this module supplies inmo24x7's job handlers and recurring jobs."""

from datetime import UTC, datetime

from followup_core.messaging.application.health import health_sweep_job
from followup_core.messaging.application.pipeline import purge_job
from followup_core.scheduling.infrastructure.queue import JobRunner, SqlAlchemyJobQueue
from followup_platform.worker import check_pool, run

from .billing.application.cost_alert import cost_alert_job
from .config import get_settings
from .container import (
    get_language_model,
    get_messaging_services,
    get_tracing,
    get_turn_tracing,
    get_usage_recorder,
    job_handlers,
    warn_if_model_unpriced,
)
from .database import SessionLocal
from .logging import configure_logging
from .observability import init_sentry
from .product import PRODUCT
from .tracing import flush

__all__ = ["build_runner", "check_pool", "main", "schedule_housekeeping"]


def build_runner() -> JobRunner:
    services = get_messaging_services()
    llm = get_language_model()
    tracing = get_turn_tracing()
    usage = get_usage_recorder()
    return JobRunner(
        SessionLocal,
        lambda session: job_handlers(session, services, llm, tracing, usage=usage),
        queue=PRODUCT,
    )


def schedule_housekeeping() -> None:
    """Recurring jobs (daily purge and LLM cost alert, 6-hourly WhatsApp health); the dedupe
    keys make every worker start agree on one per period. Each run schedules the next one."""
    now = datetime.now(UTC)
    with SessionLocal() as session:
        queue = SqlAlchemyJobQueue(session, queue=PRODUCT)
        queue.enqueue(purge_job(now))
        queue.enqueue(health_sweep_job(now))
        queue.enqueue(cost_alert_job(now))
        session.commit()


def main() -> int:
    configure_logging()
    settings = get_settings()
    init_sentry(settings, "worker")
    warn_if_model_unpriced(settings)
    return run(
        settings,
        build_runner,
        schedule_housekeeping,
        on_stop=lambda: flush(get_tracing()),  # send pending LangSmith runs
    )


if __name__ == "__main__":
    raise SystemExit(main())
