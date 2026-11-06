"""One database, one alembic.ini, one branch per package (see ARCHITECTURE.md, "Migrations").

Core revisions chain on the core branch and each product's on its own; a product revision
that needs core tables declares `depends_on` the core revision (or, before Day 8, chained to
it). Deploys run `alembic upgrade heads`. The rule: exactly one head per branch, and every
product branch reaches core.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import Script, ScriptDirectory

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "packages/core/migrations/versions"
PRODUCTS = {
    "inmo24x7": ROOT / "apps/inmo24x7/api/migrations/versions",
    "cuentas_claras": ROOT / "apps/cuentas-claras/api/migrations/versions",
}


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))


def _branch(revision: Script) -> str:
    path = Path(revision.path).resolve().parent
    if path == CORE:
        return "core"
    return next(name for name, folder in PRODUCTS.items() if path == folder)


def _reaches_core(script: ScriptDirectory, revision: Script) -> bool:
    """Through its down revisions or its depends_on, transitively."""
    seen: set[str] = set()
    pending = [revision.revision]
    while pending:
        current = script.get_revision(pending.pop())
        assert current is not None
        if current.revision in seen:
            continue
        seen.add(current.revision)
        if _branch(current) == "core":
            return True
        pending.extend(current._all_down_revisions)
    return False


def test_every_branch_has_exactly_one_head() -> None:
    script = _script()

    heads: dict[str, list[str]] = {}
    for head in script.get_heads():
        revision = script.get_revision(head)
        assert revision is not None
        heads.setdefault(_branch(revision), []).append(head)

    assert set(heads) == {"core", *(name for name, path in PRODUCTS.items() if path.exists())}
    for branch, branch_heads in heads.items():
        assert len(branch_heads) == 1, (
            f"The {branch} branch has heads {sorted(branch_heads)}: chain the newest revision "
            "on the branch's head (no merge revisions across branches are needed any more)."
        )


def test_every_product_revision_reaches_core() -> None:
    script = _script()

    for revision in script.walk_revisions():
        if _branch(revision) != "core":
            assert _reaches_core(script, revision), (
                f"{revision.revision} does not depend on any core revision: set depends_on to "
                "the core revision whose tables it needs."
            )
