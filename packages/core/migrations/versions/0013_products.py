"""two products on one platform: product on tenants, profiles per product, job queues per
product, and onboarding steps and business types defined by each product

Every existing row belongs to inmo24x7 (the only product until now) and keeps its ids:
profiles get user_id = id, so every foreign key to profiles stays valid. Slugs and owner
claims become unique per product; a user (one Supabase account, one email) gets one profile
per product; dedupe keys are unique per queue. The check constraints that listed inmo24x7's
onboarding steps and business types are dropped: each product validates its own.

From this revision on, migrations live on named branches (core, inmo24x7, cuentas_claras)
and deploys run `alembic upgrade heads`; see ARCHITECTURE.md, "Migrations".

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES

revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCTS = "('inmo24x7', 'cuentas_claras')"


def _product_column(table: str, name: str = "product") -> None:
    # The default backfills every existing row and stays for SQL written before there were
    # two products (the first product's, like the code's defaults). The other products'
    # code always sets its own value.
    op.add_column(
        table, sa.Column(name, sa.String(length=20), nullable=False, server_default="inmo24x7")
    )


def upgrade() -> None:
    _product_column("tenants")
    op.create_check_constraint("ck_tenants_product", "tenants", f"product IN {PRODUCTS}")
    op.drop_constraint("uq_tenants_slug", "tenants", type_="unique")
    op.create_unique_constraint("uq_tenants_product_slug", "tenants", ["product", "slug"])

    _product_column("profiles")
    op.add_column("profiles", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE profiles SET user_id = id")
    op.alter_column("profiles", "user_id", nullable=False)
    op.create_check_constraint("ck_profiles_product", "profiles", f"product IN {PRODUCTS}")
    op.drop_constraint("uq_profiles_email", "profiles", type_="unique")
    op.create_unique_constraint("uq_profiles_user_product", "profiles", ["user_id", "product"])
    op.create_unique_constraint("uq_profiles_email_product", "profiles", ["email", "product"])

    _product_column("tenant_owner_claims")
    op.drop_constraint("tenant_owner_claims_pkey", "tenant_owner_claims", type_="primary")
    op.create_primary_key("tenant_owner_claims_pkey", "tenant_owner_claims", ["product", "email"])

    _product_column("jobs", "queue")
    op.create_check_constraint("ck_jobs_queue", "jobs", f"queue IN {PRODUCTS}")
    op.drop_constraint("uq_jobs_dedupe_key", "jobs", type_="unique")
    op.create_unique_constraint("uq_jobs_queue_dedupe_key", "jobs", ["queue", "dedupe_key"])
    op.drop_index("ix_jobs_status_run_at", table_name="jobs")
    op.create_index("ix_jobs_queue_status_run_at", "jobs", ["queue", "status", "run_at"])

    op.drop_constraint("ck_tenant_onboarding_step", "tenant_onboarding", type_="check")
    op.drop_constraint("ck_tenant_settings_business_type", "tenant_settings", type_="check")

    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    # Only possible while every row is inmo24x7's (the second product's rows would collide).
    op.create_check_constraint(
        "ck_tenant_settings_business_type",
        "tenant_settings",
        "business_type IN ('inmobiliaria', 'red_franquicia', 'corredor', 'desarrolladora')",
    )
    op.create_check_constraint(
        "ck_tenant_onboarding_step",
        "tenant_onboarding",
        "current_step IN ('business', 'agent', 'try', 'whatsapp', 'done')",
    )

    op.drop_index("ix_jobs_queue_status_run_at", table_name="jobs")
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])
    op.drop_constraint("uq_jobs_queue_dedupe_key", "jobs", type_="unique")
    op.create_unique_constraint("uq_jobs_dedupe_key", "jobs", ["dedupe_key"])
    op.drop_constraint("ck_jobs_queue", "jobs", type_="check")
    op.drop_column("jobs", "queue")

    op.drop_constraint("tenant_owner_claims_pkey", "tenant_owner_claims", type_="primary")
    op.create_primary_key("tenant_owner_claims_pkey", "tenant_owner_claims", ["email"])
    op.drop_column("tenant_owner_claims", "product")

    op.drop_constraint("uq_profiles_email_product", "profiles", type_="unique")
    op.drop_constraint("uq_profiles_user_product", "profiles", type_="unique")
    op.create_unique_constraint("uq_profiles_email", "profiles", ["email"])
    op.drop_constraint("ck_profiles_product", "profiles", type_="check")
    op.drop_column("profiles", "user_id")
    op.drop_column("profiles", "product")

    op.drop_constraint("uq_tenants_product_slug", "tenants", type_="unique")
    op.create_unique_constraint("uq_tenants_slug", "tenants", ["slug"])
    op.drop_constraint("ck_tenants_product", "tenants", type_="check")
    op.drop_column("tenants", "product")
