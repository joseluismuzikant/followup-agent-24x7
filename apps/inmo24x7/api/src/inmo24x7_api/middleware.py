from followup_platform.middleware import RequestContextMiddleware as _RequestContextMiddleware


class RequestContextMiddleware(_RequestContextMiddleware):
    """The platform's middleware, logging on inmo24x7's logger."""

    logger_name = "inmo24x7.http"
