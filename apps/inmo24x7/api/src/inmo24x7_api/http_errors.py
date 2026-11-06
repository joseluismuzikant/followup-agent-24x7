"""Moved to followup_platform.http_errors; errors log on inmo24x7's logger."""

from fastapi import FastAPI
from followup_platform.http_errors import ApiError, error_response
from followup_platform.http_errors import register_error_handlers as _register

__all__ = ["ApiError", "error_response", "register_error_handlers"]


def register_error_handlers(app: FastAPI) -> None:
    _register(app, logger_name="inmo24x7.http")
