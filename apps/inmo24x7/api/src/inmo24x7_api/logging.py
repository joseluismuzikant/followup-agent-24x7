import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from followup_core.infrastructure import log_context

_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": "-",
            # The request or job this line belongs to (request_id, tenant_id, job_id, ...).
            **(getattr(record, "_log_context", None) or log_context.current().as_dict()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_base_factory = logging.getLogRecordFactory()


def _record_with_context(*args: Any, **kwargs: Any) -> logging.LogRecord:
    """Stamps the request/job context on the record when it is created, so a handler that
    formats it later (or in another thread) still sees it."""
    record = _base_factory(*args, **kwargs)
    record._log_context = log_context.current().as_dict()
    return record


def configure_logging() -> None:
    logging.setLogRecordFactory(_record_with_context)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    logging.getLogger("uvicorn.access").disabled = True
    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
