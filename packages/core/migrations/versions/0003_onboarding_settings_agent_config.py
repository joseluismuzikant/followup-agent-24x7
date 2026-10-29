"""onboarding, business settings, and versioned agent configuration

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires"
# Monday to Friday, 9 to 18, built in SQL so no ":" appears in a text() statement.
DEFAULT_TEAM_HOURS_SQL = """(
    SELECT jsonb_agg(
        jsonb_build_object('weekday', day, 'opens', '09:00', 'closes', '18:00')
        ORDER BY day
    )
    FROM generate_series(0, 4) AS day
)"""


def upgrade() -> None:
    op.create_table(
        "tenant_onboarding",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("current_step", sa.String(length=20), nullable=False),
        sa.Column("completed_steps", postgresql.JSONB(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.CheckConstraint(
            "current_step IN ('business', 'agent', 'try', 'whatsapp', 'done')",
            name="ck_tenant_onboarding_step",
        ),
    )
    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("business_type", sa.String(length=30), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("team_hours", postgresql.JSONB(), nullable=False),
        sa.Column("notification_emails", postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("tenant_id"),
        sa.CheckConstraint(
            "business_type IN ('inmobiliaria', 'red_franquicia', 'corredor', 'desarrolladora')",
            name="ck_tenant_settings_business_type",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(notification_emails) = 'array' "
            "AND jsonb_array_length(notification_emails) BETWEEN 1 AND 5",
            name="ck_tenant_settings_emails",
        ),
    )
    op.create_table(
        "agent_config_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_profile_id", sa.Uuid(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["created_by_profile_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "version", name="uq_agent_config_version"),
    )

    # Tenants created on Day 1 start the wizard at the agent step with the same defaults
    # a new sign-up gets, and the owner's email as the notification address.
    op.execute(
        f"""
        INSERT INTO tenant_settings
            (tenant_id, business_type, timezone, team_hours, notification_emails, updated_at)
        SELECT t.id, 'inmobiliaria', '{DEFAULT_TIMEZONE}', {DEFAULT_TEAM_HOURS_SQL},
               COALESCE(
                   (SELECT jsonb_build_array(lower(p.email)) FROM profiles p
                    WHERE p.tenant_id = t.id ORDER BY p.created_at LIMIT 1),
                   jsonb_build_array('sin-email@example.com')
               ),
               now()
        FROM tenants t
        """
    )
    op.execute(
        """
        INSERT INTO tenant_onboarding
            (tenant_id, current_step, completed_steps, finished_at, updated_at)
        SELECT t.id, 'agent', jsonb_build_object('business', to_char(
                   now() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"')), NULL, now()
        FROM tenants t
        """
    )


def downgrade() -> None:
    op.drop_table("agent_config_versions")
    op.drop_table("tenant_settings")
    op.drop_table("tenant_onboarding")
