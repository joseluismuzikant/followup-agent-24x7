"""Cuentas Claras: clients, invoices and invoice imports

The first revision of the cuentas_claras branch: a root of its own, depending on core 0013
(tenants per product). RLS on every new table, as on every table (see core 0011).

Revision ID: cc_0001
Revises:
Create Date: 2026-11-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES
from sqlalchemy.dialects import postgresql

revision: str = "cc_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("cuentas_claras",)
depends_on: str | Sequence[str] | None = "0013"


def upgrade() -> None:
    op.create_table(
        "cc_clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_key", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=200), nullable=True),
        sa.Column("cuit", sa.String(length=11), nullable=True),
        sa.Column("contact_name", sa.String(length=200), nullable=True),
        sa.Column("whatsapp", sa.String(length=20), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "cuit", name="uq_cc_clients_tenant_cuit"),
    )
    op.create_index("ix_cc_clients_tenant_name_key", "cc_clients", ["tenant_id", "name_key"])

    op.create_table(
        "cc_invoices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("cc_clients.id"), nullable=False),
        sa.Column("invoice_type", sa.String(length=1), nullable=False),
        sa.Column("point_of_sale", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.Column("paid_via", sa.String(length=20), nullable=True),
        sa.Column("payment_reference", sa.String(length=120), nullable=True),
        sa.Column("cancelled_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "invoice_type", "point_of_sale", "number", name="uq_cc_invoices_number"
        ),
        sa.CheckConstraint("invoice_type IN ('A', 'B', 'C')", name="ck_cc_invoices_type"),
        sa.CheckConstraint("currency IN ('ARS', 'USD')", name="ck_cc_invoices_currency"),
        # Day 9 adds 'promised' and Day 10 'payment_review' by widening this check.
        sa.CheckConstraint("status IN ('open', 'paid', 'cancelled')", name="ck_cc_invoices_status"),
        sa.CheckConstraint("amount > 0", name="ck_cc_invoices_amount"),
    )
    op.create_index(
        "ix_cc_invoices_tenant_status_due", "cc_invoices", ["tenant_id", "status", "due_date"]
    )
    op.create_index("ix_cc_invoices_client", "cc_invoices", ["client_id"])

    op.create_table(
        "cc_invoice_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by_profile_id", sa.Uuid(), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("failed_rows", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    op.drop_table("cc_invoice_imports")
    op.drop_table("cc_invoices")
    op.drop_table("cc_clients")
