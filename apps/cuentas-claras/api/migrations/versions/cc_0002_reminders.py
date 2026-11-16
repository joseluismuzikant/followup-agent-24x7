"""Cuentas Claras reminders: the policy, the WhatsApp templates per business, the sends and
their events, payment requests and transfer details; promised invoices and the clients'
"No enviar recordatorios"

Meta's values (template status, rejection reason, names) get room: Meta adds statuses and
its reasons are free text (core 0015 widened name_status for the same reason).

Revision ID: cc_0002
Revises: cc_0001
Create Date: 2026-11-11

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES
from sqlalchemy.dialects import postgresql

revision: str = "cc_0002"
down_revision: str | Sequence[str] | None = "cc_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "0015"


def upgrade() -> None:
    op.drop_constraint("ck_cc_invoices_status", "cc_invoices", type_="check")
    op.create_check_constraint(
        "ck_cc_invoices_status",
        "cc_invoices",
        "status IN ('open', 'promised', 'paid', 'cancelled')",
    )
    op.add_column("cc_invoices", sa.Column("promised_until", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_cc_invoices_promise",
        "cc_invoices",
        "(status = 'promised') = (promised_until IS NOT NULL)",
    )
    op.add_column(
        "cc_clients",
        sa.Column("no_reminders", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "cc_reminder_policies",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("window_preset", sa.String(length=20), nullable=False),
        sa.Column("window_start", sa.Time(), nullable=True),
        sa.Column("window_end", sa.Time(), nullable=True),
        sa.Column("skip_holidays", sa.Boolean(), nullable=False),
        sa.Column("pause_on_promise", sa.Boolean(), nullable=False),
        sa.Column("configured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cc_whatsapp_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("meta_template_id", sa.String(length=64), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "kind", "version", name="uq_cc_templates_version"),
    )
    op.create_index("ix_cc_templates_meta_id", "cc_whatsapp_templates", ["meta_template_id"])

    op.create_table(
        "cc_payment_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("cc_clients.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("invoice_ids", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cc_payment_settings",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("cbu_or_alias", sa.String(length=22), nullable=False),
        sa.Column("holder", sa.String(length=120), nullable=False),
        sa.Column("bank", sa.String(length=80), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cc_reminder_sends",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("cc_clients.id"), nullable=False),
        # The business's date: at most one reminder per client and day, ever.
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column("invoice_ids", postgresql.JSONB(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column(
            "message_id", sa.Uuid(), sa.ForeignKey("conversation_messages.id"), nullable=True
        ),
        sa.Column(
            "payment_request_id",
            sa.Uuid(),
            sa.ForeignKey("cc_payment_requests.id"),
            nullable=True,
        ),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("client_id", "day", name="uq_cc_reminder_sends_client_day"),
    )
    op.create_index("ix_cc_reminder_sends_tenant_day", "cc_reminder_sends", ["tenant_id", "day"])

    op.create_table(
        "cc_reminder_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("cc_clients.id"), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), sa.ForeignKey("cc_invoices.id"), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("offset_days", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=60), nullable=True),
        sa.Column("send_id", sa.Uuid(), sa.ForeignKey("cc_reminder_sends.id"), nullable=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_cc_reminder_events_invoice", "cc_reminder_events", ["tenant_id", "invoice_id"]
    )
    op.create_index(
        "ix_cc_reminder_events_tenant_created", "cc_reminder_events", ["tenant_id", "created_at"]
    )
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    op.drop_table("cc_reminder_events")
    op.drop_table("cc_reminder_sends")
    op.drop_table("cc_payment_settings")
    op.drop_table("cc_payment_requests")
    op.drop_table("cc_whatsapp_templates")
    op.drop_table("cc_reminder_policies")
    op.drop_column("cc_clients", "no_reminders")
    op.drop_constraint("ck_cc_invoices_promise", "cc_invoices", type_="check")
    op.drop_column("cc_invoices", "promised_until")
    op.drop_constraint("ck_cc_invoices_status", "cc_invoices", type_="check")
    op.create_check_constraint(
        "ck_cc_invoices_status", "cc_invoices", "status IN ('open', 'paid', 'cancelled')"
    )
