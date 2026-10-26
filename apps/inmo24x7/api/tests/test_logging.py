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
