"""Supabase's Data API must never reach our tables: every table in public has row level
security (no policies), and the anon / authenticated roles have no privileges. The API
connects as the table owner, which RLS does not restrict."""

from followup_core.infrastructure.db_security import REVOKE_API_ROLES
from sqlalchemy import text


def test_every_table_in_public_has_row_level_security(db_session) -> None:
    missing = (
        db_session.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity "
                "ORDER BY 1"
            )
        )
        .scalars()
        .all()
    )

    # A new table needs `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` in its own migration.
    assert missing == []
    tables = set(
        db_session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        .scalars()
        .all()
    )
    assert {"alembic_version", "checkpoints", "leads", "audit_events"} <= tables


def test_the_owner_still_reads_and_writes(db_session) -> None:
    db_session.execute(
        text(
            "INSERT INTO tenants (id, name, slug, created_at, status, trial_ends_at) "
            "VALUES (gen_random_uuid(), 'RLS', 'rls', now(), 'active', now())"
        )
    )
    assert db_session.execute(text("SELECT count(*) FROM tenants")).scalar() == 1
    db_session.rollback()


def test_supabase_api_roles_lose_every_privilege(db_session) -> None:
    for role in ("anon", "authenticated"):
        db_session.execute(
            text(
                f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') "
                f"THEN CREATE ROLE {role} NOLOGIN; END IF; END $$"
            )
        )
        db_session.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        db_session.execute(text(f"GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO {role}"))
        db_session.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {role}"))
        db_session.execute(
            text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {role}")
        )

    db_session.execute(text(REVOKE_API_ROLES))
    db_session.execute(text("CREATE TABLE public.after_lock (id int)"))

    for role in ("anon", "authenticated"):
        grants = db_session.execute(
            text(
                "SELECT count(*) FROM information_schema.role_table_grants "
                "WHERE grantee = :role AND table_schema = 'public'"
            ),
            {"role": role},
        ).scalar()
        usage = db_session.execute(
            text("SELECT has_schema_privilege(:role, 'public', 'USAGE')"), {"role": role}
        ).scalar()
        assert (grants, usage) == (0, False), role
    db_session.rollback()
