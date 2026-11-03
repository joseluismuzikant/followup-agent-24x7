"""Every core revision added after the product chain exists creates a second Alembic head
unless a product merge revision joins them (see ARCHITECTURE.md, "Migrations")."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[4]


def test_the_migration_graph_has_exactly_one_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    heads = script.get_heads()

    assert len(heads) == 1, (
        f"Alembic has {len(heads)} heads {sorted(heads)}: add a product merge revision whose "
        "down_revision is (product head, new core head)."
    )
