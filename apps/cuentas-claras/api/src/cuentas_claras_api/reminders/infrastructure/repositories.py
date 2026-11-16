from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...clients.domain.client import Client
from ...clients.infrastructure.models import ClientModel
from ...clients.infrastructure.repository import _to_domain as client_from_model
from ...invoices.domain.invoice import OWED_STATUSES, Invoice
from ...invoices.infrastructure.models import InvoiceModel
from ...invoices.infrastructure.repository import SqlAlchemyInvoiceRepository
from ...invoices.infrastructure.repository import _to_domain as invoice_from_model
from ..domain.events import DONE, Outcome, ReminderEvent, ReminderSend, SendStatus
from ..domain.policy import (
    ReminderPolicy,
    ReminderStep,
    SendWindow,
    StepKind,
    TemplateKind,
    WindowPreset,
)
from ..domain.templates import WhatsAppTemplate
from .models import (
    ReminderEventModel,
    ReminderPolicyModel,
    ReminderSendModel,
    WhatsAppTemplateModel,
)


def _step(raw: Mapping[str, Any]) -> ReminderStep:
    return ReminderStep(
        offset_days=int(raw["offset_days"]),
        kind=StepKind(raw["kind"]),
        active=bool(raw.get("active", True)),
        template_kind=TemplateKind(raw["template_kind"]) if raw.get("template_kind") else None,
        id=UUID(raw["id"]),
    )


def _step_json(step: ReminderStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "offset_days": step.offset_days,
        "kind": step.kind.value,
        "template_kind": step.template_kind.value if step.template_kind else None,
        "active": step.active,
    }


class SqlAlchemyReminderPolicyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: UUID) -> ReminderPolicy | None:
        model = self._session.get(ReminderPolicyModel, tenant_id)
        if model is None:
            return None
        return ReminderPolicy(
            tenant_id=model.tenant_id,
            steps=tuple(_step(raw) for raw in model.steps),
            window=SendWindow(
                WindowPreset(model.window_preset), model.window_start, model.window_end
            ),
            skip_holidays=model.skip_holidays,
            pause_on_promise=model.pause_on_promise,
            configured_at=model.configured_at,
            updated_at=model.updated_at,
        )

    def save(self, policy: ReminderPolicy, now: datetime) -> None:
        model = self._session.get(ReminderPolicyModel, policy.tenant_id)
        if model is None:
            model = ReminderPolicyModel(tenant_id=policy.tenant_id)
            self._session.add(model)
        model.steps = [_step_json(step) for step in policy.steps]
        model.window_preset = policy.window.preset.value
        model.window_start = policy.window.start
        model.window_end = policy.window.end
        model.skip_holidays = policy.skip_holidays
        model.pause_on_promise = policy.pause_on_promise
        model.configured_at = policy.configured_at
        model.updated_at = policy.updated_at or now
        self._session.flush()

    def is_configured(self, tenant_id: UUID) -> bool:
        model = self._session.get(ReminderPolicyModel, tenant_id)
        return model is not None and model.configured_at is not None


def _template(model: WhatsAppTemplateModel) -> WhatsAppTemplate:
    return WhatsAppTemplate(
        id=model.id,
        tenant_id=model.tenant_id,
        kind=TemplateKind(model.kind),
        version=model.version,
        name=model.name,
        body=model.body,
        status=model.status,
        created_at=model.created_at,
        language=model.language,
        category=model.category,
        meta_template_id=model.meta_template_id,
        rejection_reason=model.rejection_reason,
        submitted_at=model.submitted_at,
        last_synced_at=model.last_synced_at,
    )


class SqlAlchemyTemplateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def for_tenant(self, tenant_id: UUID) -> list[WhatsAppTemplate]:
        models = self._session.scalars(
            select(WhatsAppTemplateModel)
            .where(WhatsAppTemplateModel.tenant_id == tenant_id)
            .order_by(WhatsAppTemplateModel.kind, WhatsAppTemplateModel.version)
        )
        return [_template(model) for model in models]

    def get(self, template_id: UUID) -> WhatsAppTemplate | None:
        model = self._session.get(WhatsAppTemplateModel, template_id)
        return _template(model) if model else None

    def by_meta_id(self, meta_template_id: str) -> WhatsAppTemplate | None:
        model = self._session.scalar(
            select(WhatsAppTemplateModel).where(
                WhatsAppTemplateModel.meta_template_id == meta_template_id
            )
        )
        return _template(model) if model else None

    def save(self, template: WhatsAppTemplate) -> None:
        model = self._session.get(WhatsAppTemplateModel, template.id)
        if model is None:
            model = WhatsAppTemplateModel(
                id=template.id,
                tenant_id=template.tenant_id,
                kind=template.kind.value,
                version=template.version,
                created_at=template.created_at,
            )
            self._session.add(model)
        model.name = template.name
        model.language = template.language
        model.category = template.category
        model.body = template.body
        model.status = template.status
        model.meta_template_id = template.meta_template_id
        model.rejection_reason = template.rejection_reason
        model.submitted_at = template.submitted_at
        model.last_synced_at = template.last_synced_at
        self._session.flush()

    def tenants_with_templates(self) -> list[UUID]:
        return list(
            self._session.scalars(
                select(WhatsAppTemplateModel.tenant_id)
                .where(WhatsAppTemplateModel.meta_template_id.is_not(None))
                .distinct()
            )
        )


def _send(model: ReminderSendModel) -> ReminderSend:
    return ReminderSend(
        id=model.id,
        tenant_id=model.tenant_id,
        client_id=model.client_id,
        day=model.day,
        status=SendStatus(model.status),
        template_name=model.template_name,
        created_at=model.created_at,
        invoice_ids=tuple(UUID(item) for item in model.invoice_ids),
        steps=tuple((UUID(a), UUID(b), int(c)) for a, b, c in model.steps),
        message_id=model.message_id,
        payment_request_id=model.payment_request_id,
        error_code=model.error_code,
        sent_at=model.sent_at,
    )


class SqlAlchemyReminderLog:
    """Sends (one per client and day) and their per-invoice events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_event(self, event: ReminderEvent) -> None:
        self._session.add(
            ReminderEventModel(
                id=event.id,
                tenant_id=event.tenant_id,
                client_id=event.client_id,
                invoice_id=event.invoice_id,
                step_id=event.step_id,
                offset_days=event.offset_days,
                outcome=event.outcome.value,
                reason=event.reason[:60] if event.reason else None,
                send_id=event.send_id,
                day=event.day,
                created_at=event.created_at,
            )
        )
        self._session.flush()

    def done_steps(self, tenant_id: UUID, invoice_ids: Sequence[UUID]) -> dict[UUID, set[UUID]]:
        done: dict[UUID, set[UUID]] = defaultdict(set)
        if not invoice_ids:
            return done
        rows = self._session.execute(
            select(ReminderEventModel.invoice_id, ReminderEventModel.step_id).where(
                ReminderEventModel.tenant_id == tenant_id,
                ReminderEventModel.invoice_id.in_(invoice_ids),
                ReminderEventModel.outcome.in_([outcome.value for outcome in DONE]),
                ReminderEventModel.step_id.is_not(None),
            )
        )
        for invoice_id, step_id in rows:
            if invoice_id is not None and step_id is not None:
                done[invoice_id].add(step_id)
        return done

    def send_for(self, client_id: UUID, day: date) -> ReminderSend | None:
        model = self._session.scalar(
            select(ReminderSendModel).where(
                ReminderSendModel.client_id == client_id, ReminderSendModel.day == day
            )
        )
        return _send(model) if model else None

    def add_send(self, send: ReminderSend) -> None:
        self._session.add(
            ReminderSendModel(
                id=send.id,
                tenant_id=send.tenant_id,
                client_id=send.client_id,
                day=send.day,
                status=send.status.value,
                template_name=send.template_name,
                invoice_ids=[str(item) for item in send.invoice_ids],
                steps=[[str(a), str(b), c] for a, b, c in send.steps],
                message_id=send.message_id,
                payment_request_id=send.payment_request_id,
                error_code=send.error_code,
                created_at=send.created_at,
                sent_at=send.sent_at,
            )
        )
        self._session.flush()

    def finish_send(
        self, send_id: UUID, status: SendStatus, at: datetime, error_code: str | None = None
    ) -> None:
        model = self._session.get(ReminderSendModel, send_id)
        if model is None:
            raise LookupError(f"Reminder send {send_id} vanished.")
        model.status = status.value
        model.error_code = error_code[:60] if error_code else None
        if status is SendStatus.SENT:
            model.sent_at = at
        self._session.flush()

    def clients_sent_on(self, tenant_id: UUID, day: date) -> set[UUID]:
        """Clients that already have the day's reminder (or are getting it)."""
        return set(
            self._session.scalars(
                select(ReminderSendModel.client_id).where(
                    ReminderSendModel.tenant_id == tenant_id,
                    ReminderSendModel.day == day,
                    ReminderSendModel.status.in_(
                        [SendStatus.PENDING.value, SendStatus.SENT.value, SendStatus.FAILED.value]
                    ),
                )
            )
        )

    def sent_count(self, tenant_id: UUID, start: date, end: date) -> int:
        """Template messages that went out between `start` and `end` (exclusive)."""
        return int(
            self._session.scalar(
                select(func.count()).where(
                    ReminderSendModel.tenant_id == tenant_id,
                    ReminderSendModel.status == SendStatus.SENT.value,
                    ReminderSendModel.day >= start,
                    ReminderSendModel.day < end,
                )
            )
            or 0
        )

    def events_for(
        self, tenant_id: UUID, outcomes: Sequence[Outcome], limit: int
    ) -> list[ReminderEvent]:
        models = self._session.scalars(
            select(ReminderEventModel)
            .where(
                ReminderEventModel.tenant_id == tenant_id,
                ReminderEventModel.outcome.in_([outcome.value for outcome in outcomes]),
            )
            .order_by(ReminderEventModel.created_at.desc())
            .limit(limit)
        )
        return [
            ReminderEvent(
                tenant_id=model.tenant_id,
                client_id=model.client_id,
                outcome=Outcome(model.outcome),
                day=model.day,
                created_at=model.created_at,
                invoice_id=model.invoice_id,
                step_id=model.step_id,
                offset_days=model.offset_days,
                reason=model.reason,
                send_id=model.send_id,
                id=model.id,
            )
            for model in models
        ]


class SqlAlchemyOwedInvoices:
    """What the planner and "Lo próximo" read: owed invoices with their clients."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def owed(self, tenant_id: UUID, client_id: UUID | None = None) -> list[tuple[Invoice, Client]]:
        statement = (
            select(InvoiceModel, ClientModel)
            .join(ClientModel, ClientModel.id == InvoiceModel.client_id)
            .where(
                InvoiceModel.tenant_id == tenant_id,
                InvoiceModel.status.in_([status.value for status in OWED_STATUSES]),
            )
            .order_by(InvoiceModel.due_date, InvoiceModel.point_of_sale, InvoiceModel.number)
        )
        if client_id is not None:
            statement = statement.where(InvoiceModel.client_id == client_id)
        return [
            (invoice_from_model(invoice), client_from_model(client))
            for invoice, client in self._session.execute(statement)
        ]

    def clients(self, tenant_id: UUID, client_ids: Sequence[UUID]) -> dict[UUID, Client]:
        if not client_ids:
            return {}
        models = self._session.scalars(
            select(ClientModel).where(
                ClientModel.tenant_id == tenant_id, ClientModel.id.in_(client_ids)
            )
        )
        return {model.id: client_from_model(model) for model in models}

    def invoices(self, tenant_id: UUID, invoice_ids: Sequence[UUID]) -> list[Invoice]:
        if not invoice_ids:
            return []
        models = self._session.scalars(
            select(InvoiceModel)
            .where(InvoiceModel.tenant_id == tenant_id, InvoiceModel.id.in_(invoice_ids))
            .order_by(InvoiceModel.due_date, InvoiceModel.number)
        )
        return [invoice_from_model(model) for model in models]

    def client_by_whatsapp(self, tenant_id: UUID, e164: str) -> Client | None:
        model = self._session.scalar(
            select(ClientModel)
            .where(ClientModel.tenant_id == tenant_id, ClientModel.whatsapp == e164)
            .order_by(ClientModel.active.desc(), ClientModel.created_at)
            .limit(1)
        )
        return client_from_model(model) if model else None

    def save_invoice(self, invoice: Invoice) -> None:
        SqlAlchemyInvoiceRepository(self._session).save(invoice)
