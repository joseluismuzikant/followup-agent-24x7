import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("inmo24x7.http")

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
}


def error_response(status_code: int, code: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return error_response(422, "validation_error")

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _request: Request,
        error: StarletteHTTPException,
    ) -> JSONResponse:
        return error_response(
            error.status_code,
            _HTTP_CODES.get(error.status_code, "http_error"),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "-")
        logger.exception(
            "unhandled_exception",
            exc_info=error,
            extra={"request_id": request_id},
        )
        response = error_response(500, "internal_error")
        response.headers["X-Request-ID"] = request_id
        return response
