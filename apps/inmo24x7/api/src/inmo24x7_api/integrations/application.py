"""Integrations: connect Tokko, sync its listings every 6 hours, deliver handed-off leads to
Tokko and to the agency's webhook, and the website button's public configuration.

Jobs (all on inmo24x7's queue, retried with its backoff):
- `integrations.tokko_sync_sweep`: every 6 hours, one sync job per agency with Tokko import on;
- `integrations.tokko_sync`: one agency's sync ("Sincronizar ahora" queues one too);
- `lead.handed_off` (leads/application/notify.py, queued with the hand-off email): one
  delivery per enabled sink, each `integrations.deliver_lead` job deduplicated per lead and
  sink.
"""

import logging
import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from followup_core.messaging.infrastructure.crypto import TokenCipher
from followup_core.scheduling.domain.jobs import Job, JobQueue, NewJob, RetryLater
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ..audit import InmoAction
from ..leads.domain.errors import LeadNotFoundError
from ..leads.domain.sinks import LeadSink, LeadSinkError, QualifiedLead
from ..properties.application.rows import MESSAGES
from ..properties.domain.conditions import PropertyConditions
from ..properties.domain.property import Property, PropertyOrigin, PropertyStatus
from ..properties.domain.sources import (
    ExternalListing,
    ListingFailure,
    PropertySource,
    PropertySourceError,
)
from .domain import (
    WIDGET_DEFAULTS,
    DeliveryRepository,
    DeliveryStatus,
    Integration,
    IntegrationError,
    IntegrationRepository,
    LeadDelivery,
    Provider,
    SyncFailure,
    SyncReport,
    SyncReportRepository,
    SyncStatus,
)
from .webhook import EVENT_HANDED_OFF, EVENT_PING, new_secret, valid_url

logger = logging.getLogger("inmo24x7.integrations")

SYNC_SWEEP_JOB = "integrations.tokko_sync_sweep"
SYNC_JOB = "integrations.tokko_sync"
DELIVER_JOB = "integrations.deliver_lead"
SYNC_EVERY = timedelta(hours=6)
MAX_KEY_LENGTH = 200
MAX_LABEL_LENGTH = 40

NOT_CONNECTED = "tokko_not_connected"
KEY_INVALID = "tokko_key_invalid"
WEBHOOK_URL_INVALID = "webhook_url_invalid"
WEBHOOK_NOT_CONFIGURED = "webhook_not_configured"
WIDGET_INVALID = "widget_invalid"

Clock = Callable[[], datetime]
SourceFactory = Callable[[str], PropertySource]
SinkFactory = Callable[[Integration, str], LeadSink]
QualifiedLeads = Callable[[UUID, UUID], QualifiedLead]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _slot(now: datetime) -> int:
    return int(now.timestamp() // SYNC_EVERY.total_seconds())


def _slot_start(slot: int) -> datetime:
    return datetime.fromtimestamp(slot * SYNC_EVERY.total_seconds(), UTC)


def sync_sweep_job(now: datetime) -> NewJob:
    """The 6-hourly sweep; the dedupe key makes every worker start agree on one per slot."""
    slot = _slot(now)
    return NewJob(SYNC_SWEEP_JOB, {}, run_at=now, dedupe_key=f"tokko-sync-sweep:{slot}")


def sync_job(tenant_id: UUID, key: str) -> NewJob:
    return NewJob(
        SYNC_JOB,
        {"tenant_id": str(tenant_id)},
        dedupe_key=f"tokko-sync:{tenant_id}:{key}",
        max_attempts=3,
    )


def deliver_job(delivery: LeadDelivery) -> NewJob:
    return NewJob(
        DELIVER_JOB,
        {
            "tenant_id": str(delivery.tenant_id),
            "lead_id": str(delivery.lead_id),
            "delivery_id": str(delivery.id),
            "provider": delivery.provider.value,
        },
        dedupe_key=f"lead-delivery:{delivery.lead_id}:{delivery.provider.value}",
    )


@dataclass(frozen=True, slots=True)
class Stores:
    integrations: IntegrationRepository
    reports: SyncReportRepository
    deliveries: DeliveryRepository
    cipher: TokenCipher
    queue: JobQueue
    audit: AuditLog
    clock: Clock = utc_now


def _audit(
    stores: Stores, tenant_id: UUID, profile_id: UUID | None, action: str, **details: Any
) -> None:
    stores.audit.record(
        AuditEvent(
            tenant_id,
            stores.clock(),
            ActorKind.USER if profile_id else ActorKind.SYSTEM,
            action,
            details,
            actor_profile_id=profile_id,
        )
    )


def _blank(tenant_id: UUID, provider: Provider, now: datetime) -> Integration:
    return Integration(tenant_id, provider, False, {}, now)


# --- The panel's view -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IntegrationsView:
    tokko: Integration | None
    tokko_report: SyncReport | None
    tokko_deliveries: Sequence[LeadDelivery]
    webhook: Integration | None
    webhook_url: str | None
    webhook_deliveries: Sequence[LeadDelivery]
    widget: Integration


class GetIntegrations:
    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(self, tenant_id: UUID) -> IntegrationsView:
        stores = self._stores
        webhook = stores.integrations.get(tenant_id, Provider.WEBHOOK)
        return IntegrationsView(
            tokko=stores.integrations.get(tenant_id, Provider.TOKKO),
            tokko_report=stores.reports.last(tenant_id, Provider.TOKKO),
            tokko_deliveries=stores.deliveries.recent(tenant_id, Provider.TOKKO),
            webhook=webhook,
            webhook_url=webhook.options.get("url") if webhook else None,
            webhook_deliveries=stores.deliveries.recent(tenant_id, Provider.WEBHOOK),
            widget=EnsureWidget(stores).execute(tenant_id),
        )


# --- Tokko ----------------------------------------------------------------------------------


class ConnectTokko:
    """ "Probar conexión": one read with the key; saved (encrypted) only when it works."""

    def __init__(self, stores: Stores, check: Callable[[str], None]) -> None:
        self._stores = stores
        self._check = check

    def execute(self, tenant_id: UUID, profile_id: UUID, api_key: str) -> Integration:
        key = api_key.strip()
        if not 8 <= len(key) <= MAX_KEY_LENGTH or any(char.isspace() for char in key):
            raise IntegrationError(KEY_INVALID)
        try:
            self._check(key)
        except PropertySourceError as error:
            raise IntegrationError(error.code) from error
        stores = self._stores
        now = stores.clock()
        current = stores.integrations.get(tenant_id, Provider.TOKKO) or _blank(
            tenant_id, Provider.TOKKO, now
        )
        item = replace(
            current,
            enabled=True,
            credentials=stores.cipher.encrypt(key),
            last_error_code=None,
            updated_at=now,
        )
        if item.option("import_properties"):
            stores.queue.enqueue(sync_job(tenant_id, f"connect:{now:%Y%m%dT%H%M%S}"))
            item = replace(item, last_sync_status=SyncStatus.QUEUED)
        stores.integrations.save(item)
        _audit(stores, tenant_id, profile_id, InmoAction.INTEGRATION_CONNECTED, kind="tokko")
        return item


class UpdateTokko:
    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(
        self, tenant_id: UUID, profile_id: UUID, import_properties: bool, send_leads: bool
    ) -> Integration:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.TOKKO)
        if current is None or not current.enabled or not current.credentials:
            raise IntegrationError(NOT_CONNECTED)
        now = stores.clock()
        item = current.with_options(now, import_properties=import_properties, send_leads=send_leads)
        if import_properties and not current.option("import_properties"):
            stores.queue.enqueue(sync_job(tenant_id, f"enabled:{now:%Y%m%dT%H%M%S}"))
            item = replace(item, last_sync_status=SyncStatus.QUEUED)
        stores.integrations.save(item)
        _audit(stores, tenant_id, profile_id, InmoAction.INTEGRATION_UPDATED, kind="tokko")
        return item


class DisconnectTokko:
    """The key is deleted. Listings already imported stay, still marked as Tokko's (they
    are no longer updated); leads stop going to Tokko."""

    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(self, tenant_id: UUID, profile_id: UUID) -> None:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.TOKKO)
        if current is None:
            return
        stores.integrations.save(
            replace(current, enabled=False, credentials=None, updated_at=stores.clock())
        )
        _audit(stores, tenant_id, profile_id, InmoAction.INTEGRATION_DISCONNECTED, kind="tokko")


class RequestTokkoSync:
    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(self, tenant_id: UUID) -> Integration:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.TOKKO)
        if current is None or not current.enabled or not current.credentials:
            raise IntegrationError(NOT_CONNECTED)
        if current.last_sync_status is SyncStatus.QUEUED:
            return current  # one is already on its way
        now = stores.clock()
        stores.queue.enqueue(sync_job(tenant_id, f"now:{uuid4()}"))
        item = replace(current, last_sync_status=SyncStatus.QUEUED, updated_at=now)
        stores.integrations.save(item)
        return item


class SyncProperties:
    """One sync from a `PropertySource`: created, updated in place (conditions kept), paused
    (listed no more), failed with the reason. Nothing is deleted. When the source cannot be
    read to the end, nothing is paused: what it did not list may still be there."""

    def __init__(self, properties: Any, clock: Clock = utc_now) -> None:
        self._properties = properties
        self._clock = clock

    def execute(self, tenant_id: UUID, source: PropertySource) -> SyncReport:
        started = self._clock()
        origin = source.origin
        existing: dict[tuple[str | None, str], Property] = {
            (item.external_id, item.fields.operation.value): item
            for item in self._properties.external(tenant_id, origin)
        }
        seen: set[tuple[str | None, str]] = set()
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        failed: list[SyncFailure] = []
        error_code: str | None = None
        try:
            for listing in source.listings():
                if isinstance(listing, ListingFailure):
                    failed.append(SyncFailure(listing.external_id, listing.title, listing.reason))
                    continue
                outcome = self._upsert(tenant_id, origin, listing, existing, seen, started)
                if outcome.startswith("failed:"):
                    failed.append(
                        SyncFailure(
                            listing.external_id,
                            listing.fields.title,
                            outcome.removeprefix("failed:"),
                        )
                    )
                else:
                    counts[outcome] += 1
        except PropertySourceError as error:
            error_code = error.code
        paused = 0
        if error_code is None:
            for key, item in existing.items():
                if key not in seen and item.is_published:
                    self._properties.update(
                        item.with_fields(
                            replace(item.fields, status=PropertyStatus.PAUSED), started
                        )
                    )
                    paused += 1
        return SyncReport(
            id=uuid4(),
            tenant_id=tenant_id,
            provider=Provider.TOKKO if origin is PropertyOrigin.TOKKO else Provider(origin.value),
            started_at=started,
            finished_at=self._clock(),
            created=counts["created"],
            updated=counts["updated"],
            paused=paused,
            unchanged=counts["unchanged"],
            failed=tuple(failed),
            error_code=error_code,
        )

    def _upsert(
        self,
        tenant_id: UUID,
        origin: PropertyOrigin,
        listing: ExternalListing,
        existing: Mapping[tuple[str | None, str], Property],
        seen: set[tuple[str | None, str]],
        now: datetime,
    ) -> str:
        key = (listing.external_id, listing.fields.operation.value)
        current = existing.get(key)
        # The conditions are ours: they survive every sync.
        conditions = current.fields.conditions if current else PropertyConditions()
        fields = replace(listing.fields, conditions=conditions).clean()
        problems = fields.problems()
        if problems:
            return "failed:" + MESSAGES[problems[0]]
        seen.add(key)
        if current is None:
            self._properties.add(
                Property(
                    uuid4(),
                    tenant_id,
                    fields,
                    now,
                    now,
                    source=origin,
                    external_id=listing.external_id,
                    external_ref=listing.external_ref,
                )
            )
            return "created"
        if current.fields == fields and current.external_ref == listing.external_ref:
            return "unchanged"
        self._properties.update(
            replace(current.with_fields(fields, now), external_ref=listing.external_ref)
        )
        return "updated"


class SyncTokko:
    """The job of one agency's sync."""

    def __init__(
        self,
        stores: Stores,
        sync: SyncProperties,
        source_for: SourceFactory,
        is_active: Callable[[UUID], bool],
    ) -> None:
        self._stores = stores
        self._sync = sync
        self._source_for = source_for
        self._is_active = is_active

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.TOKKO)
        if (
            current is None
            or not current.enabled
            or not current.credentials
            or not current.option("import_properties")
            or not self._is_active(tenant_id)
        ):
            return
        report = self._sync.execute(
            tenant_id, self._source_for(stores.cipher.decrypt(current.credentials))
        )
        stores.reports.add(report)
        stores.integrations.save(
            replace(
                current,
                last_sync_at=report.finished_at,
                last_sync_status=SyncStatus.FAILED if report.error_code else SyncStatus.OK,
                last_error_code=report.error_code,
                updated_at=report.finished_at,
            )
        )
        logger.info(
            "tokko_synced",
            extra={
                "tenant_id": str(tenant_id),
                "created": report.created,
                "updated": report.updated,
                "paused": report.paused,
                "failed": len(report.failed),
                "code": report.error_code,
            },
        )


class SweepTokkoSyncs:
    """Every 6 hours: one sync job per agency, then the next sweep."""

    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def __call__(self, job: Job) -> None:
        stores = self._stores
        now = stores.clock()
        slot = _slot(now)
        for item in stores.integrations.enabled(Provider.TOKKO):
            if item.credentials and item.option("import_properties"):
                stores.queue.enqueue(sync_job(item.tenant_id, f"slot:{slot}"))
        stores.queue.enqueue(
            NewJob(
                SYNC_SWEEP_JOB,
                {},
                run_at=_slot_start(slot + 1),
                dedupe_key=f"tokko-sync-sweep:{slot + 1}",
            )
        )


# --- Leads out ------------------------------------------------------------------------------


def _sink_ready(item: Integration | None) -> bool:
    if item is None or not item.enabled or not item.credentials:
        return False
    if item.provider is Provider.TOKKO:
        return bool(item.option("send_leads"))
    return bool(item.options.get("url"))


class QueueLeadDeliveries:
    """The hand-off's fan-out: one delivery per enabled sink, once per lead and sink."""

    def __init__(self, stores: Stores, is_active: Callable[[UUID], bool]) -> None:
        self._stores = stores
        self._is_active = is_active

    def __call__(self, job: Job) -> None:
        tenant_id = UUID(job.payload["tenant_id"])
        lead_id = UUID(job.payload["lead_id"])
        if not self._is_active(tenant_id):
            return
        stores = self._stores
        now = stores.clock()
        for provider in (Provider.TOKKO, Provider.WEBHOOK):
            if not _sink_ready(stores.integrations.get(tenant_id, provider)):
                continue
            delivery = LeadDelivery(
                id=uuid4(),
                tenant_id=tenant_id,
                provider=provider,
                event=EVENT_HANDED_OFF,
                status=DeliveryStatus.PENDING,
                created_at=now,
                updated_at=now,
                lead_id=lead_id,
            )
            if stores.queue.enqueue(deliver_job(delivery)):
                stores.deliveries.add(delivery)


class DeliverLead:
    """One delivery attempt. A retryable failure keeps the attempt on record and lets the
    queue try again with its backoff (`RetryLater`); a permanent one, or the last attempt,
    marks it failed."""

    def __init__(
        self,
        stores: Stores,
        qualified: QualifiedLeads,
        sink_for: SinkFactory,
    ) -> None:
        self._stores = stores
        self._qualified = qualified
        self._sink_for = sink_for

    def __call__(self, job: Job) -> RetryLater | None:
        stores = self._stores
        delivery = stores.deliveries.get(UUID(job.payload["delivery_id"]))
        if delivery is None or delivery.status is DeliveryStatus.DELIVERED:
            return None  # deleted with its contact, or already delivered
        integration = stores.integrations.get(delivery.tenant_id, delivery.provider)
        if not _sink_ready(integration) or delivery.lead_id is None:
            self._finish(delivery, DeliveryStatus.FAILED, error_code="integration_disabled")
            return None
        assert integration is not None and integration.credentials is not None
        try:
            lead = self._qualified(delivery.tenant_id, delivery.lead_id)
        except LeadNotFoundError:
            self._finish(delivery, DeliveryStatus.FAILED, error_code="lead_not_found")
            return None
        sink = self._sink_for(integration, stores.cipher.decrypt(integration.credentials))
        try:
            result = sink.deliver(lead, delivery.id, delivery.event)
        except LeadSinkError as error:
            last = not error.retry or job.attempts >= job.max_attempts
            self._finish(
                delivery,
                DeliveryStatus.FAILED if last else DeliveryStatus.RETRYING,
                status_code=error.status_code,
                error_code=error.code,
                integration=integration,
            )
            return None if last else RetryLater(error.code)
        self._finish(
            delivery,
            DeliveryStatus.DELIVERED,
            status_code=result.status_code,
            integration=integration,
        )
        return None

    def _finish(
        self,
        delivery: LeadDelivery,
        status: DeliveryStatus,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        integration: Integration | None = None,
    ) -> None:
        stores = self._stores
        now = stores.clock()
        stores.deliveries.save(
            replace(
                delivery,
                status=status,
                attempts=delivery.attempts + 1,
                status_code=status_code,
                error_code=error_code,
                updated_at=now,
                delivered_at=now if status is DeliveryStatus.DELIVERED else None,
            )
        )
        if integration is not None:
            stores.integrations.save(
                replace(
                    integration,
                    last_delivery_at=now,
                    last_delivery_status=status,
                    last_error_code=error_code,
                    updated_at=now,
                )
            )
        logger.info(
            "lead_delivery",
            extra={
                "tenant_id": str(delivery.tenant_id),
                "lead_id": str(delivery.lead_id),
                "kind": delivery.provider.value,
                "status": status.value,
                "code": error_code,
            },
        )


# --- Webhook --------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WebhookSaved:
    integration: Integration
    # Shown once, when it is generated.
    secret: str | None


class ConfigureWebhook:
    def __init__(self, stores: Stores, allow_http: bool = False) -> None:
        self._stores = stores
        self._allow_http = allow_http

    def execute(self, tenant_id: UUID, profile_id: UUID, url: str, enabled: bool) -> WebhookSaved:
        url = url.strip()
        if not valid_url(url, allow_http=self._allow_http):
            raise IntegrationError(WEBHOOK_URL_INVALID)
        stores = self._stores
        now = stores.clock()
        current = stores.integrations.get(tenant_id, Provider.WEBHOOK) or _blank(
            tenant_id, Provider.WEBHOOK, now
        )
        secret = None if current.credentials else new_secret()
        item = replace(
            current.with_options(now, url=url),
            enabled=enabled,
            credentials=stores.cipher.encrypt(secret) if secret else current.credentials,
        )
        stores.integrations.save(item)
        _audit(stores, tenant_id, profile_id, InmoAction.INTEGRATION_UPDATED, kind="webhook")
        return WebhookSaved(item, secret)


class RotateWebhookSecret:
    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(self, tenant_id: UUID, profile_id: UUID) -> WebhookSaved:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.WEBHOOK)
        if current is None or not current.options.get("url"):
            raise IntegrationError(WEBHOOK_NOT_CONFIGURED)
        secret = new_secret()
        item = replace(
            current, credentials=stores.cipher.encrypt(secret), updated_at=stores.clock()
        )
        stores.integrations.save(item)
        _audit(
            stores,
            tenant_id,
            profile_id,
            InmoAction.INTEGRATION_UPDATED,
            kind="webhook",
            event="secret_rotated",
        )
        return WebhookSaved(item, secret)


class DeleteWebhook:
    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(self, tenant_id: UUID, profile_id: UUID) -> None:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.WEBHOOK)
        if current is None:
            return
        stores.integrations.save(
            replace(current, enabled=False, credentials=None, options={}, updated_at=stores.clock())
        )
        _audit(stores, tenant_id, profile_id, InmoAction.INTEGRATION_DISCONNECTED, kind="webhook")


class SendWebhookTest:
    """ "Enviar prueba": a signed `ping` right away, in the delivery log like any other."""

    def __init__(
        self,
        stores: Stores,
        ping: Callable[[Integration, str, UUID], Any],
    ) -> None:
        self._stores = stores
        self._ping = ping

    def execute(self, tenant_id: UUID) -> LeadDelivery:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.WEBHOOK)
        if current is None or not current.credentials or not current.options.get("url"):
            raise IntegrationError(WEBHOOK_NOT_CONFIGURED)
        now = stores.clock()
        delivery = LeadDelivery(
            id=uuid4(),
            tenant_id=tenant_id,
            provider=Provider.WEBHOOK,
            event=EVENT_PING,
            status=DeliveryStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        try:
            result = self._ping(current, stores.cipher.decrypt(current.credentials), delivery.id)
            done = replace(
                delivery,
                status=DeliveryStatus.DELIVERED,
                attempts=1,
                status_code=result.status_code,
                delivered_at=stores.clock(),
            )
        except LeadSinkError as error:
            done = replace(
                delivery,
                status=DeliveryStatus.FAILED,
                attempts=1,
                status_code=error.status_code,
                error_code=error.code,
            )
        stores.deliveries.add(replace(done, updated_at=stores.clock()))
        return done


# --- Website button -------------------------------------------------------------------------

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
POSITIONS = ("right", "left")


class EnsureWidget:
    """The button's settings, with its public id (created the first time it is asked for)."""

    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(self, tenant_id: UUID) -> Integration:
        stores = self._stores
        current = stores.integrations.get(tenant_id, Provider.WIDGET)
        if current is not None and current.public_id:
            return current
        now = stores.clock()
        item = replace(
            current or _blank(tenant_id, Provider.WIDGET, now),
            enabled=True,
            public_id=secrets.token_urlsafe(9),
            updated_at=now,
        )
        stores.integrations.save(item)
        return item


class SaveWidget:
    def __init__(self, stores: Stores) -> None:
        self._stores = stores

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        *,
        enabled: bool,
        color: str,
        text_color: str,
        position: str,
        label: str,
    ) -> Integration:
        label = " ".join(label.split())
        if (
            not _HEX.fullmatch(color)
            or not _HEX.fullmatch(text_color)
            or position not in POSITIONS
            or not 1 <= len(label) <= MAX_LABEL_LENGTH
        ):
            raise IntegrationError(WIDGET_INVALID)
        stores = self._stores
        current = EnsureWidget(stores).execute(tenant_id)
        item = replace(
            current.with_options(
                stores.clock(),
                color=color.lower(),
                text_color=text_color.lower(),
                position=position,
                label=label,
            ),
            enabled=enabled,
        )
        stores.integrations.save(item)
        _audit(stores, tenant_id, profile_id, InmoAction.INTEGRATION_UPDATED, kind="widget")
        return item


@dataclass(frozen=True, slots=True)
class PublicWidget:
    """Only public data: what any visitor of the agency's website can see anyway."""

    agency_name: str
    # Digits for wa.me; None while WhatsApp is not connected (the button stays hidden).
    phone: str | None
    color: str
    text_color: str
    position: str
    label: str


class GetPublicWidget:
    def __init__(
        self,
        integrations: IntegrationRepository,
        business_name: Callable[[UUID], str],
        whatsapp_number: Callable[[UUID], str | None],
        is_active: Callable[[UUID], bool],
    ) -> None:
        self._integrations = integrations
        self._business_name = business_name
        self._whatsapp_number = whatsapp_number
        self._is_active = is_active

    def execute(self, public_id: str) -> PublicWidget | None:
        if not 4 <= len(public_id) <= 32:
            return None
        item = self._integrations.by_public_id(public_id)
        if item is None or not item.enabled or not self._is_active(item.tenant_id):
            return None
        number = self._whatsapp_number(item.tenant_id)
        digits = "".join(char for char in number or "" if char.isdigit()) or None
        options = {**WIDGET_DEFAULTS, **item.options}
        return PublicWidget(
            agency_name=self._business_name(item.tenant_id),
            phone=digits,
            color=str(options["color"]),
            text_color=str(options["text_color"]),
            position=str(options["position"]),
            label=str(options["label"]),
        )


@dataclass(frozen=True, slots=True)
class IntegrationUseCases:
    get: GetIntegrations
    connect_tokko: ConnectTokko
    update_tokko: UpdateTokko
    disconnect_tokko: DisconnectTokko
    sync_tokko: RequestTokkoSync
    configure_webhook: ConfigureWebhook
    rotate_secret: RotateWebhookSecret
    delete_webhook: DeleteWebhook
    test_webhook: SendWebhookTest
    save_widget: SaveWidget
    deliveries: DeliveryRepository
    # Whether WhatsApp is connected and its number (the button needs one).
    whatsapp_number: Callable[[UUID], str | None]
