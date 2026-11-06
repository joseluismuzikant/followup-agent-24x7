"""invitation-only accounts: accounts (the forced password change), invitations (the emailed
link, only its token's hash) and dev_passwords (AUTH_MODE=dev's stand-in for Supabase Auth)

Every person with a profile today gets an account that does not have to change its password.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("email", name="uq_accounts_email"),
    )
    op.execute(
        """
        INSERT INTO accounts (user_id, email, must_change_password, created_at)
        SELECT DISTINCT ON (user_id) user_id, email, false, created_at
        FROM profiles
        ORDER BY user_id, created_at
        ON CONFLICT DO NOTHING
        """
    )
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("product", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
        sa.CheckConstraint(
            "product IN ('inmo24x7', 'cuentas_claras')", name="ck_invitations_product"
        ),
    )
    op.create_index("ix_invitations_product_email", "invitations", ["product", "email"])
    op.create_table(
        "dev_passwords",
        sa.Column("email", sa.String(length=320), primary_key=True),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
    )
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    op.drop_table("dev_passwords")
    op.drop_index("ix_invitations_product_email", table_name="invitations")
    op.drop_table("invitations")
    op.drop_table("accounts")
