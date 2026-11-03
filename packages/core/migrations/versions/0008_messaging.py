"""messaging: WhatsApp connections, inbound events and outbound deliveries

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("content_type", sa.String(length=20), nullable=False, server_default="text"),
    )
    op.create_table(
        "whatsapp_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("display_phone_number", sa.String(length=40), nullable=True),
        sa.Column("verified_name", sa.String(length=200), nullable=True),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("sender", sa.String(length=10), nullable=False),
        sa.Column("template_name", sa.String(length=100), nullable=False),
        sa.Column("template_language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=15), nullable=False),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_whatsapp_connections_tenant"),
        sa.UniqueConstraint("phone_number_id", name="uq_whatsapp_connections_phone_number"),
        sa.CheckConstraint(
            "status IN ('connected', 'disconnected', 'error')",
            name="ck_whatsapp_connections_status",
        ),
        sa.CheckConstraint("sender IN ('cloud', 'log')", name="ck_whatsapp_connections_sender"),
    )
    op.create_table(
        "whatsapp_inbound_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("wamid", sa.String(length=200), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("wa_id", sa.String(length=32), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("choice_id", sa.String(length=256), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wamid", name="uq_whatsapp_inbound_events_wamid"),
        sa.CheckConstraint(
            "status IN ('pending', 'processed', 'ignored')",
            name="ck_whatsapp_inbound_events_status",
        ),
    )
    op.create_index(
        "ix_whatsapp_inbound_events_thread",
        "whatsapp_inbound_events",
        ["tenant_id", "wa_id", "status", "sent_at"],
    )
    op.create_table(
        "whatsapp_outbound",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "message_id", sa.Uuid(), sa.ForeignKey("conversation_messages.id"), nullable=False
        ),
        sa.Column("part", sa.Integer(), nullable=False),
        sa.Column("wa_id", sa.String(length=32), nullable=False),
        # The Cloud API request body, rendered when the turn was stored.
        sa.Column("body", postgresql.JSONB(), nullable=False),
        sa.Column("wamid", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wamid", name="uq_whatsapp_outbound_wamid"),
        sa.UniqueConstraint("message_id", "part", name="uq_whatsapp_outbound_message_part"),
        sa.CheckConstraint(
            "status IN ('queued', 'sent', 'delivered', 'read', 'failed')",
            name="ck_whatsapp_outbound_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("whatsapp_outbound")
    op.drop_index("ix_whatsapp_inbound_events_thread", table_name="whatsapp_inbound_events")
    op.drop_table("whatsapp_inbound_events")
    op.drop_table("whatsapp_connections")
    op.drop_column("conversation_messages", "content_type")
