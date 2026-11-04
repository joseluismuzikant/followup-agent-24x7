import json
import logging
from uuid import uuid4

from followup_core.infrastructure import log_context
from inmo24x7_api.logging import JsonFormatter


def _record(extra: dict[str, object] | None = None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="inmo24x7.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="test_event",
        args=(),
        exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_json_formatter_includes_request_context() -> None:
    with log_context.scope(request_id="request-123"):
        payload = json.loads(JsonFormatter().format(_record()))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "inmo24x7.test"
    assert payload["message"] == "test_event"
    assert payload["request_id"] == "request-123"
    assert payload["timestamp"]
    assert "tenant_id" not in payload


def test_bound_tenant_and_job_reach_every_line() -> None:
    tenant_id, job_id = uuid4(), uuid4()
    with log_context.scope(job_id=job_id, job_kind="whatsapp.process"):
        log_context.bind(tenant_id=tenant_id)
        payload = json.loads(JsonFormatter().format(_record()))
        # A call site's own value wins.
        explicit = json.loads(JsonFormatter().format(_record({"tenant_id": "other"})))

    assert payload["tenant_id"] == str(tenant_id)
    assert payload["job_id"] == str(job_id)
    assert payload["job_kind"] == "whatsapp.process"
    assert payload["request_id"] == "-"
    assert explicit["tenant_id"] == "other"
    # Outside a scope nothing is bound.
    log_context.bind(tenant_id=tenant_id)
    assert "tenant_id" not in json.loads(JsonFormatter().format(_record()))


def test_request_completed_has_the_tenant_bound_by_a_dependency(
    client, auth, caplog, monkeypatch
) -> None:
    owner = uuid4()
    token = auth.register(owner, "owner@example.com")
    client.post(
        "/me/sign-up",
        json={"business_name": "Inmo Log", "business_type": "inmobiliaria"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Alembic's logging config (the migration fixture) disables existing loggers.
    monkeypatch.setattr(logging.getLogger("inmo24x7.http"), "disabled", False)
    caplog.set_level(logging.INFO, logger="inmo24x7.http")
    caplog.clear()
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    tenant_id = response.json()["tenant"]["id"]

    line = next(r for r in caplog.records if r.getMessage() == "request_completed")
    payload = json.loads(JsonFormatter().format(line))
    assert payload["tenant_id"] == tenant_id
    assert payload["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_exception_is_logged_once(monkeypatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from inmo24x7_api.http_errors import register_error_handlers
    from inmo24x7_api.middleware import RequestContextMiddleware

    calls: list[str] = []

    def fake_exception(self, message, *args, **kwargs) -> None:
        calls.append(str(message))

    monkeypatch.setattr(logging.Logger, "exception", fake_exception)

    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {"code": "internal_error"}
    assert response.headers["X-Request-ID"]
    assert calls.count("unhandled_exception") == 1
    assert "request_failed" not in calls
