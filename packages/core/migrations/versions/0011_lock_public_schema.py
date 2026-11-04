"""lock the public schema: row level security on every table, nothing for Supabase's API roles

Supabase publishes the public schema through its Data API, reachable with the anon key that
ships in our panel bundle. We never use the Data API (the API connects as the table owner,
which RLS does not restrict), so: RLS on every table with no policies, and no privileges or
default privileges for `anon` and `authenticated`. The role part only runs where those roles
exist (Supabase), so plain Postgres (local, CI) migrates the same way. Turning off the Data API
in the dashboard is still required (docs/go-live.md); this is the second lock.

Core and product revisions are separate branches, so product tables may be created after
this one runs: every product merge revision applies the same (idempotent) SQL again. New
tables must enable RLS in their own migration: tests/test_rls.py fails otherwise.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-06

"""

from collections.abc import Sequence

from alembic import op
from followup_core.infrastructure.db_security import ENABLE_RLS, REVOKE_API_ROLES

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISABLE_RLS = ENABLE_RLS.replace("ENABLE ROW LEVEL SECURITY", "DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute(ENABLE_RLS)
    op.execute(REVOKE_API_ROLES)


def downgrade() -> None:
    # The revoked privileges are not granted back: nothing of ours used them.
    op.execute(DISABLE_RLS)
