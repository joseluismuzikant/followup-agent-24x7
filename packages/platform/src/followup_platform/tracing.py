"""LangSmith tracing for agent turns. Observability only: the app behaves the same with it
off, and a LangSmith error, timeout or missing key never fails or slows down a turn
(runs are posted from a background thread).

Turned on by LANGSMITH_TRACING=true plus LANGSMITH_API_KEY. Turns go to the LangSmith agent
named by LANGSMITH_AGENT_ID and LANGSMITH_AGENT_ENVIRONMENT when both are set, otherwise to a
project (LANGSMITH_PROJECT, or inmo24x7-dev / inmo24x7-prod). Lead messages carry names,
phone numbers, emails and DNIs, so unless LANGSMITH_REDACT_PII=false every input and
output is masked by `anonymize` before it leaves the process.
"""

import logging
import re
from dataclasses import dataclass
from uuid import UUID

from followup_core.conversation.infrastructure.langgraph_runtime import TurnTracing
from langsmith import Client
from langsmith.address import AgentAddress, agent_address
from langsmith.anonymizer import create_anonymizer

from .settings import Settings

CLIENT_TIMEOUT_MS = 5_000
_PROJECT_SUFFIX = {"development": "dev", "production": "prod"}

logger = logging.getLogger("followup.tracing")

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
    # Exactly one of the two is set.
    project_name: str | None
    address: AgentAddress | None
    ui_url: str


class TracingConfigError(ValueError):
    pass


def product_tag(settings: Settings) -> str:
    """The product as LangSmith shows it: "inmo24x7", "cuentas-claras"."""
    return settings.product.value.replace("_", "-")


def project_name(settings: Settings) -> str:
    return settings.langsmith_project or (
        f"{product_tag(settings)}-{_PROJECT_SUFFIX.get(settings.app_env, settings.app_env)}"
    )


def agent(settings: Settings) -> AgentAddress | None:
    """The agent address from LANGSMITH_AGENT_ID and LANGSMITH_AGENT_ENVIRONMENT, if set."""
    agent_id = settings.langsmith_agent_id
    environment = settings.langsmith_agent_environment
    if not agent_id and not environment:
        return None
    if not agent_id or not environment:
        raise TracingConfigError(
            "LANGSMITH_AGENT_ID and LANGSMITH_AGENT_ENVIRONMENT must be set together."
        )
    try:
        return agent_address(agent_id, environment)
    except Exception as error:  # invalid id or environment
        raise TracingConfigError(str(error)) from error


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
        address = agent(settings)
        client = Client(
            api_url=settings.langsmith_endpoint or None,
            api_key=settings.langsmith_api_key,
            anonymizer=anonymize if settings.langsmith_redact_pii else None,
            timeout_ms=CLIENT_TIMEOUT_MS,
        )
    except Exception as error:  # e.g. an invalid agent address or sampling rate
        logger.warning("langsmith_disabled", extra={"detail": str(error)})
        return None
    project = None if address else project_name(settings)
    logger.info(
        "langsmith_tracing_active",
        extra={
            "agent": f"{address['id']}/{address['environment']}" if address else None,
            "project": project,
            "redact_pii": settings.langsmith_redact_pii,
        },
    )
    return Tracing(
        client=client, project_name=project, address=address, ui_url=settings.langsmith_ui_url
    )


def turn_tracing(
    tracing: Tracing | None, settings: Settings, run_name: str = ""
) -> TurnTracing | None:
    """`run_name` names the product's agent turn ("inmo24x7.lead_turn")."""
    if tracing is None:
        return None
    return TurnTracing(
        client=tracing.client,
        project_name=tracing.project_name,
        address=tracing.address,
        run_name=run_name or f"{product_tag(settings)}.turn",
        tags=(product_tag(settings), settings.app_env),
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
