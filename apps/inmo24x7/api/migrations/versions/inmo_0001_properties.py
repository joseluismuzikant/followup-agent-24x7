"""inmo24x7 properties and their imports (S7)

The first product revision: it chains to the core head, as every product chain must.

Revision ID: inmo_0001
Revises: 0006
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "inmo_0001"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "properties",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("address", sa.String(length=200), nullable=False),
        sa.Column("operation", sa.String(length=10), nullable=False),
        sa.Column("zone", sa.String(length=80), nullable=False),
        sa.Column("price", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rooms", sa.Integer(), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("search_text", sa.String(length=300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "link", name="uq_properties_tenant_link"),
        sa.CheckConstraint("operation IN ('sale', 'rent')", name="ck_properties_operation"),
        sa.CheckConstraint("currency IN ('ARS', 'USD')", name="ck_properties_currency"),
        sa.CheckConstraint("status IN ('published', 'paused')", name="ck_properties_status"),
        sa.CheckConstraint("price > 0", name="ck_properties_price"),
        sa.CheckConstraint("rooms >= 1", name="ck_properties_rooms"),
    )
    op.create_index(
        "ix_properties_tenant_status_operation",
        "properties",
        ["tenant_id", "status", "operation"],
    )
    op.create_table(
        "property_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by_profile_id", sa.Uuid(), nullable=True),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("created", sa.Integer(), nullable=False),
        sa.Column("updated", sa.Integer(), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("failed_rows", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("property_imports")
    op.drop_index("ix_properties_tenant_status_operation", table_name="properties")
    op.drop_table("properties")
