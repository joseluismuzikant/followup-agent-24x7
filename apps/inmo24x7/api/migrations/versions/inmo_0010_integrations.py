"""inmo24x7 integrations: Tokko Broker, the lead webhook and the website button

- `properties.source` (manual / tokko), `external_id` (Tokko's id) and `external_ref` (the
  agency's code). A Tokko property for sale and for rent is two listings with the same
  public link, so the link stays unique only among the agency's own listings, and Tokko's
  are unique by (id, operation).
- `leads.source`: "web_button" when the lead came from the website's WhatsApp button.
- `inmo_integrations`: one row per agency and integration; `credentials` is TokenCipher
  ciphertext (Tokko's API key, the webhook secret); `public_id` is the button's id.
- `inmo_sync_reports`: each sync's created / updated / paused / failed.
- `inmo_lead_deliveries`: each delivery's status (never the payload).

Revision ID: inmo_0010
Revises: inmo_0009
Create Date: 2026-11-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES
from sqlalchemy.dialects import postgresql

revision: str = "inmo_0010"
down_revision: str | Sequence[str] | None = "inmo_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("source", sa.String(10), nullable=False, server_default=sa.text("'manual'")),
    )
    op.add_column("properties", sa.Column("external_id", sa.String(64), nullable=True))
    op.add_column("properties", sa.Column("external_ref", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_properties_source", "properties", "source IN ('manual', 'tokko')"
    )
    op.drop_constraint("uq_properties_tenant_link", "properties", type_="unique")
    op.create_index(
        "uq_properties_tenant_link",
        "properties",
        ["tenant_id", "link"],
        unique=True,
        postgresql_where=sa.text("source = 'manual'"),
    )
    op.create_index(
        "uq_properties_external",
        "properties",
        ["tenant_id", "source", "external_id", "operation"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.add_column("leads", sa.Column("source", sa.String(20), nullable=True))

    op.create_table(
        "inmo_integrations",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("provider", sa.String(20), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "options",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("credentials", sa.Text(), nullable=True),
        sa.Column("public_id", sa.String(32), nullable=True, unique=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(10), nullable=True),
        sa.Column("last_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_delivery_status", sa.String(10), nullable=True),
        sa.Column("last_error_code", sa.String(40), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('tokko', 'webhook', 'widget')", name="ck_integrations_provider"
        ),
    )
    op.create_table(
        "inmo_sync_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Integer(), nullable=False),
        sa.Column("unchanged", sa.Integer(), nullable=False),
        sa.Column("failed", postgresql.JSONB(), nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
    )
    op.create_index(
        "ix_sync_reports_tenant_started", "inmo_sync_reports", ["tenant_id", "started_at"]
    )
    op.create_table(
        "inmo_lead_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'retrying', 'delivered', 'failed')",
            name="ck_lead_deliveries_status",
        ),
    )
    op.create_index(
        "ix_lead_deliveries_tenant_provider",
        "inmo_lead_deliveries",
        ["tenant_id", "provider", "created_at"],
    )
    op.create_index("ix_lead_deliveries_lead", "inmo_lead_deliveries", ["lead_id"])
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    op.drop_table("inmo_lead_deliveries")
    op.drop_table("inmo_sync_reports")
    op.drop_table("inmo_integrations")
    op.drop_column("leads", "source")
    op.drop_index("uq_properties_external", table_name="properties")
    op.drop_index("uq_properties_tenant_link", table_name="properties")
    # Tokko's listings share links across operations: they go before the link is unique again.
    tokko = "SELECT id FROM properties WHERE source <> 'manual'"
    op.execute(f"DELETE FROM lead_property_matches WHERE property_id IN ({tokko})")  # noqa: S608
    op.execute(f"UPDATE visits SET property_id = NULL WHERE property_id IN ({tokko})")  # noqa: S608
    op.execute(f"DELETE FROM properties WHERE id IN ({tokko})")  # noqa: S608
    op.create_unique_constraint("uq_properties_tenant_link", "properties", ["tenant_id", "link"])
    op.drop_constraint("ck_properties_source", "properties", type_="check")
    op.drop_column("properties", "external_ref")
    op.drop_column("properties", "external_id")
    op.drop_column("properties", "source")
