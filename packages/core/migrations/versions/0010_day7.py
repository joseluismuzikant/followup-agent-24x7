"""day 7: plans and suspension, owner claims, audit log, Embedded Signup progress, WhatsApp
connection health, and hourly webhook counters

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants", sa.Column("plan", sa.String(length=10), nullable=False, server_default="trial")
    )
    op.add_column("tenants", sa.Column("suspended_reason", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_tenants_plan", "tenants", "plan IN ('trial', 'pro')")

    op.create_table(
        "tenant_owner_claims",
        sa.Column("email", sa.String(length=320), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_kind", sa.String(length=10), nullable=False),
        sa.Column("actor_profile_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=200), nullable=True, unique=True),
        sa.CheckConstraint(
            "actor_kind IN ('user', 'admin', 'system')", name="ck_audit_events_actor_kind"
        ),
    )
    op.create_index("ix_audit_events_tenant_at", "audit_events", ["tenant_id", sa.text("at DESC")])

    for column in (
        sa.Column("business_id", sa.String(length=64), nullable=True),
        sa.Column("quality_rating", sa.String(length=20), nullable=True),
        sa.Column("name_status", sa.String(length=20), nullable=True),
        sa.Column(
            "business_verification",
            sa.String(length=10),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("failing_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("whatsapp_connections", column)

    op.create_table(
        "whatsapp_signups",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("waba_id", sa.String(length=64), nullable=False),
        sa.Column("phone_number_id", sa.String(length=64), nullable=False),
        sa.Column("business_id", sa.String(length=64), nullable=True),
        sa.Column("step", sa.String(length=15), nullable=False),
        sa.Column("token_encrypted", sa.Text(), nullable=True),
        sa.Column("pin_encrypted", sa.Text(), nullable=False),
        sa.Column("last_error_code", sa.String(length=40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "webhook_counters",
        sa.Column("hour", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("kind", sa.String(length=20), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    # "waiting_connection": parts held while the connection is in error.
    op.alter_column(
        "whatsapp_outbound",
        "status",
        type_=sa.String(length=20),
        existing_type=sa.String(length=10),
        existing_nullable=False,
    )
    op.drop_constraint("ck_whatsapp_outbound_status", "whatsapp_outbound", type_="check")
    op.create_check_constraint(
        "ck_whatsapp_outbound_status",
        "whatsapp_outbound",
        "status IN ('queued', 'waiting_connection', 'sent', 'delivered', 'read', 'failed')",
    )
    # Salud del sistema: failed sends by Meta code in the last 24 hours.
    op.create_index(
        "ix_whatsapp_outbound_status_updated", "whatsapp_outbound", ["status", "updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_outbound_status_updated", table_name="whatsapp_outbound")
    op.execute("UPDATE whatsapp_outbound SET status = 'queued' WHERE status = 'waiting_connection'")
    op.drop_constraint("ck_whatsapp_outbound_status", "whatsapp_outbound", type_="check")
    op.create_check_constraint(
        "ck_whatsapp_outbound_status",
        "whatsapp_outbound",
        "status IN ('queued', 'sent', 'delivered', 'read', 'failed')",
    )
    op.alter_column(
        "whatsapp_outbound",
        "status",
        type_=sa.String(length=10),
        existing_type=sa.String(length=20),
        existing_nullable=False,
    )
    op.drop_table("webhook_counters")
    op.drop_table("whatsapp_signups")
    for name in (
        "last_health_check_at",
        "failing_since",
        "business_verification",
        "name_status",
        "quality_rating",
        "business_id",
    ):
        op.drop_column("whatsapp_connections", name)
    op.drop_index("ix_audit_events_tenant_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("tenant_owner_claims")
    op.drop_constraint("ck_tenants_plan", "tenants", type_="check")
    op.drop_column("tenants", "suspended_at")
    op.drop_column("tenants", "suspended_reason")
    op.drop_column("tenants", "plan")
