"""Meta's WhatsApp webhook. It only verifies, stores and enqueues: Meta gets its 200 in
milliseconds and the agent runs in the worker."""

import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from followup_core.messaging.application.pipeline import IngestWebhook
from starlette.concurrency import run_in_threadpool

from .http_errors import ApiError, error_response

logger = logging.getLogger("inmo24x7.webhooks")

SIGNATURE_HEADER = "X-Hub-Signature-256"


class WebhookCounters(Protocol):
    """Hourly counts for Salud del sistema."""

    def increment(self, kind: str, at: datetime) -> None: ...


def valid_signature(secret: str, body: bytes, header: str | None) -> bool:
    """HMAC-SHA256 of the raw body with the app secret, compared in constant time."""
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def build_webhook_router(
    ingest_factory: Callable[..., IngestWebhook],
    secrets_factory: Callable[..., tuple[str, str]],
    counters_factory: Callable[..., WebhookCounters],
) -> APIRouter:
    router = APIRouter(tags=["webhooks"])

    @router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
    def verify(
        secrets: Annotated[tuple[str, str], Depends(secrets_factory)],
        mode: Annotated[str, Query(alias="hub.mode")] = "",
        token: Annotated[str, Query(alias="hub.verify_token")] = "",
        challenge: Annotated[str, Query(alias="hub.challenge")] = "",
    ) -> PlainTextResponse:
        _, verify_token = secrets
        if mode == "subscribe" and hmac.compare_digest(token.encode(), verify_token.encode()):
            return PlainTextResponse(challenge)
        logger.warning("whatsapp_verify_rejected")
        raise ApiError(403, "forbidden")

    @router.post("/webhooks/whatsapp", response_model=dict[str, str])
    async def receive(
        request: Request,
        secrets: Annotated[tuple[str, str], Depends(secrets_factory)],
        ingest: Annotated[IngestWebhook, Depends(ingest_factory)],
        counters: Annotated[WebhookCounters, Depends(counters_factory)],
    ) -> dict[str, str] | JSONResponse:
        # The signature covers the exact bytes Meta sent: read them before any parsing.
        body = await request.body()
        app_secret, _ = secrets
        if not valid_signature(app_secret, body, request.headers.get(SIGNATURE_HEADER)):
            logger.warning(
                "whatsapp_signature_rejected",
                extra={"has_signature": SIGNATURE_HEADER.lower() in request.headers},
            )
            # Returned, not raised, so the counter is committed.
            await run_in_threadpool(counters.increment, "signature_rejected", datetime.now(UTC))
            return error_response(401, "invalid_signature")
        try:
            payload = json.loads(body)
        except ValueError as error:
            raise ApiError(400, "bad_request") from error
        if not isinstance(payload, dict):
            raise ApiError(400, "bad_request")
        # The database work is synchronous: keep it off the event loop.
        await run_in_threadpool(counters.increment, "received", datetime.now(UTC))
        result = await run_in_threadpool(ingest.execute, payload)
        logger.info(
            "whatsapp_webhook",
            extra={
                "queued": result.queued,
                "duplicates": result.duplicates,
                "ignored": result.ignored,
                "statuses": result.statuses,
                "account_updates": result.account_updates,
            },
        )
        return {"status": "ok"}

    return router
