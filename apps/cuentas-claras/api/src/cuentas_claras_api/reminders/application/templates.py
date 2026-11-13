"""The business's templates in its WABA: created when it connects WhatsApp (one per step
kind plus the one for several invoices), each version submitted by a job, and their
status kept in sync by Meta's `message_template_status_update` webhook and, as a fallback,
a sync every 6 hours.

An edit in C4 is a new version, submitted for review; the previous approved version keeps
going out until the new one is approved."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID

from followup_core.messaging.domain.outbound import SendError
from followup_core.messaging.domain.repositories import ConnectionRepository
from followup_core.messaging.domain.webhook import TemplateStatusUpdate
from followup_core.scheduling.domain.jobs import Job, JobQueue, NewJob, RetryLater
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import CuentasAction
from ..domain.policy import TemplateKind
from ..domain.repositories import TemplateRepository
from ..domain.templates import (
    DEFAULT_BODIES,
    TemplateStatus,
    WhatsAppTemplate,
    newest,
    validate_body,
)
from ..infrastructure.template_graph import TemplateGraphFor
from .context import Clock, utc_now

logger = logging.getLogger("cuentas_claras.templates")

ENSURE_TEMPLATES_JOB = "reminders.templates.ensure"
SUBMIT_TEMPLATE_JOB = "reminders.templates.submit"
SYNC_TEMPLATES_JOB = "reminders.templates.sync"
SYNC_SWEEP_JOB = "reminders.templates.sync_sweep"
SYNC_INTERVAL = timedelta(hours=6)


def ensure_templates_job(tenant_id: UUID, now: datetime) -> NewJob:
    return NewJob(
        ENSURE_TEMPLATES_JOB,
        {"tenant_id": str(tenant_id)},
        dedupe_key=f"templates-ensure:{tenant_id}:{now:%Y%m%d%H%M}",
        max_attempts=5,
    )


def submit_job(template: WhatsAppTemplate) -> NewJob:
    """One per version and text (an unsubmitted version edited again is submitted again)."""
    text = hashlib.sha256(template.body.encode()).hexdigest()[:12]
    return NewJob(
        SUBMIT_TEMPLATE_JOB,
        {"template_id": str(template.id)},
        dedupe_key=f"templates-submit:{template.id}:{text}",
        max_attempts=6,
    )


def _slot(at: datetime) -> datetime:
    return at.replace(hour=at.hour - at.hour % 6, minute=0, second=0, microsecond=0)


def sync_sweep_job(at: datetime) -> NewJob:
    slot = _slot(at)
    return NewJob(
        SYNC_SWEEP_JOB,
        {},
        run_at=max(slot, at),
        dedupe_key=f"templates-sweep:{slot:%Y%m%d%H}",
        max_attempts=3,
    )


class EnsureTemplates:
    """Every kind gets its first version, and every version not yet at Meta is submitted.
    Nothing happens until the business has a WhatsApp connection."""

    def __init__(
        self,
        templates: TemplateRepository,
        connections: ConnectionRepository,
        queue: JobQueue,
        clock: Clock = utc_now,
    ) -> None:
        self._templates = templates
        self._connections = connections
        self._queue = queue
        self._clock = clock

    def __call__(self, job: Job) -> None:
        self.execute(UUID(job.payload["tenant_id"]))

    def execute(self, tenant_id: UUID) -> int:
        now = self._clock()
        versions = self._templates.for_tenant(tenant_id)
        for kind in TemplateKind:
            if not any(item.kind is kind for item in versions):
                created = WhatsAppTemplate.new(tenant_id, kind, 1, DEFAULT_BODIES[kind], now)
                self._templates.save(created)
                versions.append(created)
        connection = self._connections.get_by_tenant(tenant_id)
        if connection is None or not connection.is_connected:
            return 0
        queued = 0
        for kind in TemplateKind:
            latest = newest([item for item in versions if item.kind is kind])
            if latest is not None and latest.status == TemplateStatus.NOT_SUBMITTED.value:
                queued += int(self._queue.enqueue(submit_job(latest)))
        return queued


class SubmitTemplate:
    def __init__(
        self,
        templates: TemplateRepository,
        connections: ConnectionRepository,
        graph_for: TemplateGraphFor,
        panel_url: str,
        business_name: Callable[[UUID], str],
        clock: Clock = utc_now,
    ) -> None:
        self._templates = templates
        self._connections = connections
        self._graph_for = graph_for
        self._panel_url = panel_url
        self._business_name = business_name
        self._clock = clock

    def __call__(self, job: Job) -> RetryLater | None:
        return self.execute(UUID(job.payload["template_id"]))

    def execute(self, template_id: UUID) -> RetryLater | None:
        template = self._templates.get(template_id)
        if template is None or template.submitted:
            return None
        connection = self._connections.get_by_tenant(template.tenant_id)
        if connection is None or not connection.is_connected:
            return None  # EnsureTemplates submits it once WhatsApp is connected
        now = self._clock()
        request = template.meta_request(self._panel_url, self._business_name(template.tenant_id))
        try:
            meta_id, status = self._graph_for(connection).create(connection, request)
        except SendError as error:
            if error.retryable:
                return RetryLater(f"meta_{error.code}")
            self._templates.save(
                replace(
                    template,
                    status=TemplateStatus.SUBMIT_FAILED.value,
                    rejection_reason=f"meta_{error.code}",
                    last_synced_at=now,
                )
            )
            logger.warning("template_submit_failed", extra={"meta_code": error.code})
            return None
        self._templates.save(
            replace(
                template,
                meta_template_id=meta_id,
                status=status,
                rejection_reason=None,
                submitted_at=now,
                last_synced_at=now,
            )
        )
        logger.info("template_submitted", extra={"kind": template.kind.value, "status": status})
        return None


class SyncTemplates:
    """Reads the WABA's templates and updates ours by Meta id (or by name and language for
    a version whose creation answer was lost)."""

    def __init__(
        self,
        templates: TemplateRepository,
        connections: ConnectionRepository,
        graph_for: TemplateGraphFor,
        clock: Clock = utc_now,
    ) -> None:
        self._templates = templates
        self._connections = connections
        self._graph_for = graph_for
        self._clock = clock

    def __call__(self, job: Job) -> RetryLater | None:
        try:
            self.execute(UUID(job.payload["tenant_id"]))
        except SendError as error:
            if error.retryable:
                return RetryLater(f"meta_{error.code}")
            logger.warning("template_sync_failed", extra={"meta_code": error.code})
        return None

    def execute(self, tenant_id: UUID) -> int:
        connection = self._connections.get_by_tenant(tenant_id)
        if connection is None or not connection.is_connected:
            return 0
        listed = self._graph_for(connection).list(connection)
        by_id = {item.id: item for item in listed}
        by_name = {(item.name, item.language): item for item in listed}
        now = self._clock()
        changed = 0
        for template in self._templates.for_tenant(tenant_id):
            found = by_id.get(template.meta_template_id or "") or by_name.get(
                (template.name, template.language)
            )
            if found is None:
                continue
            if found.status != template.status or found.id != template.meta_template_id:
                changed += 1
            self._templates.save(
                template.with_status(found.status, found.rejected_reason, now, found.id)
            )
        return changed


class SyncSweep:
    def __init__(
        self,
        tenants: Callable[[], list[UUID]],
        queue: JobQueue,
        clock: Clock = utc_now,
    ) -> None:
        self._tenants = tenants
        self._queue = queue
        self._clock = clock

    def __call__(self, job: Job) -> None:
        now = self._clock()
        slot = _slot(now)
        for tenant_id in self._tenants():
            self._queue.enqueue(
                NewJob(
                    SYNC_TEMPLATES_JOB,
                    {"tenant_id": str(tenant_id)},
                    dedupe_key=f"templates-sync:{tenant_id}:{slot:%Y%m%d%H}",
                    max_attempts=3,
                )
            )
        self._queue.enqueue(sync_sweep_job(slot + SYNC_INTERVAL))


class ApplyTemplateStatus:
    """Meta's webhook: a template of ours was approved, rejected, paused, ..."""

    def __init__(self, templates: TemplateRepository, clock: Clock = utc_now) -> None:
        self._templates = templates
        self._clock = clock

    def __call__(self, update: TemplateStatusUpdate) -> bool:
        template = self._templates.by_meta_id(update.template_id)
        if template is None:
            return False
        self._templates.save(template.with_status(update.status, update.reason, self._clock()))
        logger.info(
            "template_status_updated", extra={"kind": template.kind.value, "status": update.status}
        )
        return True


class SaveTemplateText:
    """C4's "Editar texto": a new version for review (an unsubmitted one is just edited)."""

    def __init__(
        self,
        templates: TemplateRepository,
        queue: JobQueue,
        audit: AuditLog,
        clock: Clock = utc_now,
    ) -> None:
        self._templates = templates
        self._queue = queue
        self._audit = audit
        self._clock = clock

    def execute(
        self, tenant_id: UUID, profile_id: UUID, kind: TemplateKind, body: str
    ) -> WhatsAppTemplate:
        text = validate_body(body)
        now = self._clock()
        versions = [item for item in self._templates.for_tenant(tenant_id) if item.kind is kind]
        latest = newest(versions)
        if latest is not None and latest.body == text:
            return latest
        if latest is not None and not latest.submitted:
            saved = replace(latest, body=text, status=TemplateStatus.NOT_SUBMITTED.value)
        else:
            version = latest.version + 1 if latest else 1
            saved = WhatsAppTemplate.new(tenant_id, kind, version, text, now)
        self._templates.save(saved)
        self._queue.enqueue(ensure_templates_job(tenant_id, now))
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER,
                CuentasAction.TEMPLATE_EDITED,
                {"kind": kind.value, "version": str(saved.version)},
                actor_profile_id=profile_id,
            )
        )
        return saved
