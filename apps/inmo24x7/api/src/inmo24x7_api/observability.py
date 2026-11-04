"""Error reports to Sentry for the API and the worker (SENTRY_DSN; empty = off).

What reaches Sentry is operational: the error, its stack trace (without local variables), the
request's method and path, and ids (request_id, tenant_id, job_id). Never request bodies,
query strings, cookies, headers outside a short list, or the user beyond their profile id;
every string also goes through the same anonymizer as LangSmith (emails, phones, DNIs) plus
bearer tokens. Expected outcomes (4xx ApiErrors, validation errors, the 24-hour window) are
not errors and are dropped.
"""

import logging
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk
from fastapi.exceptions import RequestValidationError
from followup_core.infrastructure import log_context
from sentry_sdk.integrations.anthropic import AnthropicIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.langchain import LangchainIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.openai import OpenAIIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings
from .http_errors import ApiError
from .tracing import anonymize

logger = logging.getLogger("inmo24x7.observability")

SAFE_HEADERS = frozenset({"user-agent", "content-type", "x-request-id"})
# Outcomes the product expects; they are answered, not broken.
EXPECTED_CODES = frozenset({"outside_service_window"})
BEARER = re.compile(r"(?i)\bbearer\s+[\w.~+/=-]+")
JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+")
# Parts of an event that may carry free text; ids, versions and SDK data are left alone.
_TEXT_PARTS = ("message", "logentry", "exception", "breadcrumbs", "extra", "tags")


def scrub_text(value: str) -> str:
    value = BEARER.sub("Bearer <token>", value)
    value = JWT.sub("<jwt>", value)
    return anonymize(value)  # type: ignore[return-value]


def scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {key: scrub(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(item) for item in value]
    return value


def without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def is_expected(event: Mapping[str, Any], hint: Mapping[str, Any]) -> bool:
    exc_info = hint.get("exc_info")
    error = exc_info[1] if exc_info else None
    if isinstance(error, ApiError):
        return error.status_code < 500 or error.code in EXPECTED_CODES
    if isinstance(error, RequestValidationError):
        return True
    if isinstance(error, StarletteHTTPException):
        return error.status_code < 500
    text = str(event.get("message") or "") + str((event.get("logentry") or {}).get("message", ""))
    return any(code in text for code in EXPECTED_CODES)


def _request(request: Mapping[str, Any]) -> dict[str, Any]:
    headers = request.get("headers") or {}
    return {
        "method": request.get("method"),
        "url": without_query(str(request.get("url", ""))),
        "headers": {name: value for name, value in headers.items() if name.lower() in SAFE_HEADERS},
    }


def make_before_send(service: str):
    def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
        if is_expected(event, hint):
            return None
        if "request" in event:
            event["request"] = _request(event["request"])
        user = event.get("user") or {}
        event["user"] = {"id": user["id"]} if user.get("id") else {}
        event["tags"] = {**(event.get("tags") or {}), **log_context.current().as_dict()}
        event["tags"]["service"] = service
        for part in _TEXT_PARTS:
            if part in event:
                event[part] = scrub(event[part])
        return event

    return before_send


def before_breadcrumb(crumb: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    data = crumb.get("data") or {}
    if isinstance(data.get("url"), str):
        data["url"] = without_query(data["url"])
    data.pop("http.query", None)
    data.pop("http.fragment", None)
    crumb["data"] = scrub(data)
    if isinstance(crumb.get("message"), str):
        crumb["message"] = scrub_text(crumb["message"])
    return crumb


def init_sentry(settings: Settings, service: str) -> bool:
    """Starts the SDK once per process; False (and nothing sent) without SENTRY_DSN."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.commit,
        server_name=service,
        # What the SDK may collect at all; before_send below is the second lock.
        data_collection={
            "user_info": False,
            "cookies": {"mode": "off"},
            "http_headers": {"request": {"mode": "allowlist", "terms": sorted(SAFE_HEADERS)}},
            "http_bodies": [],
            "url_query_params": {"mode": "off"},
            "gen_ai": {"inputs": False, "outputs": False},
            "database_query_data": False,
            # Frame locals could hold message text.
            "stack_frame_variables": False,
        },
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[
            # Only unhandled errors (500); 502/503 answers are ours and logged where needed.
            StarletteIntegration(failed_request_status_codes={500}),
            FastApiIntegration(failed_request_status_codes={500}),
            SqlalchemyIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Prompts and replies are lead messages: never captured, even as spans.
        disabled_integrations=[LangchainIntegration(), AnthropicIntegration(), OpenAIIntegration()],
        before_send=make_before_send(service),  # type: ignore[arg-type]
        before_breadcrumb=before_breadcrumb,  # type: ignore[arg-type]
    )
    logger.info(
        "sentry_active",
        extra={"service": service, "traces_sample_rate": settings.sentry_traces_sample_rate},
    )
    return True
