"""llm_usage.audio_seconds: voice-note transcriptions (operation "transcribe")

A transcription is billed by the audio's length, not by tokens: its row has zero tokens and
the seconds here (NULL for model calls). The audio itself is never stored anywhere; the
transcript is the message's text.

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("llm_usage", sa.Column("audio_seconds", sa.Float(), nullable=True))
    op.drop_constraint("ck_llm_usage_operation", "llm_usage", type_="check")
    op.create_check_constraint(
        "ck_llm_usage_operation",
        "llm_usage",
        "operation IN ('extract', 'compose_reply', 'transcribe')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_usage WHERE operation = 'transcribe'")
    op.drop_constraint("ck_llm_usage_operation", "llm_usage", type_="check")
    op.create_check_constraint(
        "ck_llm_usage_operation", "llm_usage", "operation IN ('extract', 'compose_reply')"
    )
    op.drop_column("llm_usage", "audio_seconds")
