"""inmo24x7 leads: one per conversation thread, status history, shown properties and visits

Revision ID: inmo_0002
Revises: inmo_0001
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "inmo_0002"
down_revision: str | Sequence[str] | None = "inmo_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEAD_STATUSES = "'qualifying', 'visit_proposed', 'human_requested', 'visit_confirmed'"


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column(
            "thread_id",
            sa.Uuid(),
            sa.ForeignKey("conversation_threads.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("thread_key", sa.String(length=200), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("is_test", sa.Boolean(), nullable=False),
        sa.Column("visitor_name", sa.String(length=80), nullable=True),
        sa.Column("contact", sa.String(length=120), nullable=True),
        sa.Column("answers", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("handed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hand_off_reason", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({LEAD_STATUSES})", name="ck_leads_status"),
    )
    op.create_index("ix_leads_tenant_last_activity", "leads", ["tenant_id", "last_activity_at"])
    op.create_table(
        "lead_status_changes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({LEAD_STATUSES})", name="ck_lead_status_changes_status"),
        sa.UniqueConstraint("lead_id", "position", name="uq_lead_status_changes_position"),
    )
    op.create_table(
        "lead_property_matches",
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), primary_key=True),
        sa.Column("property_id", sa.Uuid(), sa.ForeignKey("properties.id"), primary_key=True),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_lead_property_matches_property", "lead_property_matches", ["property_id"])
    op.create_table(
        "visits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("property_id", sa.Uuid(), sa.ForeignKey("properties.id"), nullable=True),
        sa.Column("property_label", sa.String(length=320), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'cancelled')", name="ck_visits_status"
        ),
    )
    op.create_index("ix_visits_lead", "visits", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_visits_lead", table_name="visits")
    op.drop_table("visits")
    op.drop_index("ix_lead_property_matches_property", table_name="lead_property_matches")
    op.drop_table("lead_property_matches")
    op.drop_table("lead_status_changes")
    op.drop_index("ix_leads_tenant_last_activity", table_name="leads")
    op.drop_table("leads")
