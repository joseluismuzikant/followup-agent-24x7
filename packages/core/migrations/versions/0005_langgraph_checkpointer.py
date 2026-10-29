"""LangGraph Postgres checkpointer tables

The DDL is ported from langgraph-checkpoint-postgres 3.2.0 (`BasePostgresSaver.MIGRATIONS`,
versions 0 to 9) so deploys only run `alembic upgrade head`; the API never calls
`PostgresSaver.setup()`. Indexes are created without CONCURRENTLY so this runs inside the
migration transaction. `checkpoint_migrations` is filled so the saver sees itself as up to
date. Upgrading the checkpoint package needs a new migration with the new MIGRATIONS entries.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKPOINT_MIGRATIONS_APPLIED = 10


def upgrade() -> None:
    op.execute("CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY)")
    op.execute(
        """
        CREATE TABLE checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint JSONB NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE checkpoint_blobs (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL,
            version TEXT NOT NULL,
            type TEXT NOT NULL,
            blob BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE checkpoint_writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            type TEXT,
            blob BYTEA NOT NULL,
            task_path TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """
    )
    op.execute("CREATE INDEX checkpoints_thread_id_idx ON checkpoints(thread_id)")
    op.execute("CREATE INDEX checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)")
    op.execute("CREATE INDEX checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)")
    op.execute(
        "INSERT INTO checkpoint_migrations (v) "
        f"SELECT generate_series(0, {CHECKPOINT_MIGRATIONS_APPLIED - 1})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE checkpoint_writes")
    op.execute("DROP TABLE checkpoint_blobs")
    op.execute("DROP TABLE checkpoints")
    op.execute("DROP TABLE checkpoint_migrations")
