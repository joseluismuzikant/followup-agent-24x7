import json
import logging

from inmo24x7_api.logging import JsonFormatter, request_id_context


def test_json_formatter_includes_request_context() -> None:
    token = request_id_context.set("request-123")
    try:
        record = logging.LogRecord(
            name="inmo24x7.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="test_event",
            args=(),
            exc_info=None,
        )
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_context.reset(token)

    assert payload["level"] == "INFO"
    assert payload["logger"] == "inmo24x7.test"
    assert payload["message"] == "test_event"
    assert payload["request_id"] == "request-123"
    assert payload["timestamp"]


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
