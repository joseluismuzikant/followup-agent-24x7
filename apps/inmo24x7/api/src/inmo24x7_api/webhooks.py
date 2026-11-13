"""Moved to followup_platform.routers.webhooks (shared with Cuentas Claras); inmo24x7's
webhook logs on its own logger, as before."""

from collections.abc import Callable

from fastapi import APIRouter
from followup_core.messaging.application.pipeline import IngestWebhook
from followup_platform.routers.webhooks import SIGNATURE_HEADER, WebhookCounters, valid_signature
from followup_platform.routers.webhooks import build_webhook_router as _build

__all__ = ["SIGNATURE_HEADER", "WebhookCounters", "build_webhook_router", "valid_signature"]


def build_webhook_router(
    ingest_factory: Callable[..., IngestWebhook],
    secrets_factory: Callable[..., tuple[str, str]],
    counters_factory: Callable[..., WebhookCounters],
) -> APIRouter:
    return _build(ingest_factory, secrets_factory, counters_factory, "inmo24x7.webhooks")
