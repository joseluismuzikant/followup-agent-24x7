import logging
import time
from uuid import uuid4

from followup_core.infrastructure import log_context
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("inmo24x7.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()

        # The tenant dependency binds tenant_id into this context, so request_completed has
        # it. When the endpoint raises, the context stays open for the unhandled-error handler
        # (it runs after this middleware, in the same task; the next request is a new task).
        token = log_context.start(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        log_context.end(token)
        return response
