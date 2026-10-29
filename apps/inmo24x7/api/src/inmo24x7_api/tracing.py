"""LangSmith tracing for agent turns. Observability only: the app behaves the same with it
off, and a LangSmith error, timeout or missing key never fails or slows down a turn
(runs are posted from a background thread).

Turned on by LANGSMITH_TRACING=true plus LANGSMITH_API_KEY. Lead messages carry names,
phone numbers, emails and DNIs, so unless LANGSMITH_REDACT_PII=false every input and
output is masked by `anonymize` before it leaves the process.
"""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from followup_core.conversation.infrastructure.langgraph_runtime import TurnTracing
from langsmith import Client
from langsmith.anonymizer import create_anonymizer

from .config import Settings

RUN_NAME = "inmo24x7.lead_turn"
PRODUCT_TAG = "inmo24x7"
CLIENT_TIMEOUT_MS = 5_000
_PROJECT_SUFFIX = {"development": "dev", "production": "prod"}

logger = logging.getLogger("inmo24x7.tracing")

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Argentine numbers with or without +54, the mobile 9, the area code (with or without 0
# and parentheses) and the old 15 prefix: "+54 9 11 1234-5678", "011 15 1234-5678",
# "(0351) 456-7890", "1123456789". Not inside longer tokens such as UUIDs.
PHONE = re.compile(
    r"(?<![\w-])(?:\+?54[\s-]*)?(?:9[\s-]*)?(?:\(?0?\d{2,4}\)?[\s-]*)?(?:15[\s-]*)?"
    r"\d{3,4}[\s-]?\d{4}(?![\w-])"
)
# DNI: 7 or 8 digits, with or without thousands dots ("30.123.456", "30123456").
DNI = re.compile(r"(?<![\w.-])(?:\d{1,2}\.\d{3}\.\d{3}|\d{7,8})(?![\w-]|\.\d)")

anonymize = create_anonymizer(
    [
        {"pattern": EMAIL, "replace": "<email>"},
        {"pattern": PHONE, "replace": "<phone>"},
        {"pattern": DNI, "replace": "<dni>"},
    ]
)


@dataclass(frozen=True, slots=True)
class Tracing:
    client: Client
    project_name: str
    ui_url: str


def project_name(settings: Settings) -> str:
    return settings.langsmith_project or (
        f"{PRODUCT_TAG}-{_PROJECT_SUFFIX.get(settings.app_env, settings.app_env)}"
    )


def build_tracing(settings: Settings) -> Tracing | None:
    """The configured LangSmith client, or None when tracing is off or cannot start."""
    if not settings.langsmith_tracing:
        return None
    if not settings.langsmith_api_key:
        logger.warning(
            "langsmith_disabled",
            extra={"detail": "LANGSMITH_TRACING is on but LANGSMITH_API_KEY is empty."},
        )
        return None
    try:
        client = Client(
            api_url=settings.langsmith_endpoint or None,
            api_key=settings.langsmith_api_key,
            anonymizer=anonymize if settings.langsmith_redact_pii else None,
            timeout_ms=CLIENT_TIMEOUT_MS,
        )
    except Exception as error:  # e.g. an invalid LANGSMITH_TRACING_SAMPLING_RATE
        logger.warning("langsmith_disabled", extra={"detail": str(error)})
        return None
    project = project_name(settings)
    logger.info(
        "langsmith_tracing_active",
        extra={"project": project, "redact_pii": settings.langsmith_redact_pii},
    )
    return Tracing(client=client, project_name=project, ui_url=settings.langsmith_ui_url)


def turn_tracing(tracing: Tracing | None, settings: Settings) -> TurnTracing | None:
    if tracing is None:
        return None
    return TurnTracing(
        client=tracing.client,
        project_name=tracing.project_name,
        run_name=RUN_NAME,
        tags=(PRODUCT_TAG, settings.app_env),
        metadata={"app_version": settings.version, "commit": settings.commit},
    )


def trace_url(ui_url: str, run_id: UUID | None) -> str | None:
    """Link to a run in the LangSmith UI. LANGSMITH_UI_URL is the project's page."""
    if not ui_url or run_id is None:
        return None
    return f"{ui_url}/r/{run_id}?poll=true"


def flush(tracing: Tracing | None) -> None:
    """Sends pending runs on shutdown; never raises."""
    if tracing is None:
        return
    try:
        tracing.client.flush(timeout=CLIENT_TIMEOUT_MS / 1000)
    except Exception as error:
        logger.warning("langsmith_flush_failed", extra={"detail": str(error)})
