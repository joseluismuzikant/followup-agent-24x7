"""What the API and the worker send to Sentry: errors with ids, never personal data."""

import logging
from dataclasses import replace
from uuid import uuid4

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from followup_core.infrastructure import log_context
from inmo24x7_api.config import get_settings
from inmo24x7_api.http_errors import ApiError, register_error_handlers
from inmo24x7_api.middleware import RequestContextMiddleware
from inmo24x7_api.observability import (
    before_breadcrumb,
    init_sentry,
    make_before_send,
    scrub_text,
)
from sentry_sdk.transport import Transport

before_send = make_before_send("api")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Escribime a ana.perez+casa@gmail.com", "Escribime a <email>"),
        ("Mi cel es +54 9 11 5555-1234", "Mi cel es <phone>"),
        ("llamame al 011 15 4444-5555", "llamame al <phone>"),
        ("(0351) 456-7890", "<phone>"),
        ("1123456789", "<phone>"),
        ("DNI 30.123.456", "DNI <dni>"),
        # A bare 8-digit DNI also looks like a phone number: either way it is gone.
        ("dni 30123456", "dni <phone>"),
        ("Authorization: Bearer abc.def-123_xyz", "Authorization: Bearer <token>"),
        ("token eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJl here", "token <jwt> here"),
        # Ids stay readable.
        (
            "tenant 9b2f1c5e-8a5d-4d8e-9a43-1c0f6b8e2a11",
            "tenant 9b2f1c5e-8a5d-4d8e-9a43-1c0f6b8e2a11",
        ),
    ],
)
def test_scrub_text(text: str, expected: str) -> None:
    assert scrub_text(text) == expected


def _event(**extra) -> dict:
    return {
        "message": "failed for ana@example.com",
        "exception": {"values": [{"type": "ValueError", "value": "bad phone +54 9 11 5555-1234"}]},
        "request": {
            "method": "POST",
            "url": "https://api.example.com/leads?q=ana@example.com",
            "query_string": "q=ana@example.com",
            "data": {"text": "Hola, soy Ana, DNI 30.123.456"},
            "cookies": {"session": "secret"},
            "headers": {
                "Authorization": "Bearer abc",
                "Cookie": "x=1",
                "User-Agent": "Mozilla/5.0",
                "X-Request-ID": "req-1",
            },
        },
        "user": {"id": "profile-1", "email": "ana@example.com", "ip_address": "1.2.3.4"},
        "breadcrumbs": {"values": [{"message": "sent to ana@example.com"}]},
        **extra,
    }


def test_events_lose_bodies_queries_cookies_headers_and_pii() -> None:
    event = before_send(_event(), {})

    assert event is not None
    assert event["request"] == {
        "method": "POST",
        "url": "https://api.example.com/leads",
        "headers": {"User-Agent": "Mozilla/5.0", "X-Request-ID": "req-1"},
    }
    assert event["user"] == {"id": "profile-1"}
    assert event["message"] == "failed for <email>"
    assert event["exception"]["values"][0]["value"] == "bad phone <phone>"
    assert event["breadcrumbs"]["values"][0]["message"] == "sent to <email>"
    assert "ana" not in str(event).lower()


def test_events_are_tagged_with_the_request_or_job_context() -> None:
    tenant_id, job_id = uuid4(), uuid4()
    with log_context.scope(request_id="req-9", job_id=job_id, job_kind="whatsapp.send"):
        log_context.bind(tenant_id=tenant_id, channel="whatsapp")
        event = make_before_send("worker")(_event(), {})

    assert event is not None
    assert event["tags"] == {
        "request_id": "req-9",
        "tenant_id": str(tenant_id),
        "job_id": str(job_id),
        "job_kind": "whatsapp.send",
        "channel": "whatsapp",
        "service": "worker",
    }


@pytest.mark.parametrize(
    "error",
    [
        ApiError(404, "lead_not_found"),
        ApiError(422, "validation_error"),
        ApiError(409, "outside_service_window"),
        RequestValidationError([]),
    ],
)
def test_expected_outcomes_are_not_sent(error: Exception) -> None:
    hint = {"exc_info": (type(error), error, None)}

    assert before_send(_event(), hint) is None


def test_server_errors_and_messages_about_the_window_are_told_apart() -> None:
    error = ApiError(502, "whatsapp_signup_failed")
    assert before_send(_event(), {"exc_info": (ApiError, error, None)}) is not None
    assert before_send(_event(message="send failed: outside_service_window"), {}) is None


def test_breadcrumbs_lose_query_strings_and_pii() -> None:
    crumb = before_breadcrumb(
        {
            "category": "httplib",
            "message": "GET to ana@example.com",
            "data": {
                "url": "https://graph.facebook.com/v26.0/x?access_token=abc",
                "http.query": "x",
            },
        },
        {},
    )

    assert crumb is not None
    assert crumb["data"] == {"url": "https://graph.facebook.com/v26.0/x"}
    assert crumb["message"] == "GET to <email>"


def test_sentry_is_off_without_a_dsn() -> None:
    assert init_sentry(replace(get_settings(), sentry_dsn=""), "api") is False
    assert not sentry_sdk.get_client().is_active()


class Capture(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict] = []

    def capture_envelope(self, envelope) -> None:
        for item in envelope.items:
            if item.type == "event" and item.payload.json is not None:
                self.events.append(item.payload.json)


@pytest.fixture
def sentry_events(monkeypatch):
    """The real SDK with a fake transport: what would be sent, for one test."""
    transport = Capture()
    settings = replace(get_settings(), sentry_dsn="https://key@sentry.invalid/1")
    original_init = sentry_sdk.init
    monkeypatch.setattr(
        sentry_sdk, "init", lambda **kwargs: original_init(transport=transport, **kwargs)
    )
    assert init_sentry(settings, "api") is True
    yield transport.events
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # back to the inactive client


def test_an_unhandled_error_is_sent_once_with_its_request_id(sentry_events) -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.post("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("could not reach ana@example.com")

    @app.get("/missing")
    def missing() -> dict[str, str]:
        raise ApiError(404, "lead_not_found")

    # Alembic's logging config (other tests) may have disabled this logger.
    logging.getLogger("inmo24x7.http").disabled = False
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/boom?q=secret", json={"text": "Hola, soy Ana"})
        assert client.get("/missing").status_code == 404
    sentry_sdk.flush()

    assert response.status_code == 500
    assert len(sentry_events) == 1
    event = sentry_events[0]
    assert event["tags"]["request_id"] == response.headers["X-Request-ID"]
    assert event["tags"]["service"] == "api"
    assert event["exception"]["values"][-1]["value"] == "could not reach <email>"
    assert "Hola" not in str(event) and "secret" not in str(event)
    frames = event["exception"]["values"][-1]["stacktrace"]["frames"]
    assert all("vars" not in frame for frame in frames)


def test_an_error_log_line_is_an_event_and_a_warning_is_not(sentry_events) -> None:
    log = logging.getLogger("inmo24x7.test_observability")
    log.disabled = False
    with log_context.scope(job_id="job-1", job_kind="whatsapp.process"):
        log.warning("job_failed", extra={"code": "LlmUnavailableError"})
        log.error("job_dead", extra={"code": "LlmUnavailableError"})
    sentry_sdk.flush()

    assert [event["logentry"]["message"] for event in sentry_events] == ["job_dead"]
    assert sentry_events[0]["tags"]["job_kind"] == "whatsapp.process"
