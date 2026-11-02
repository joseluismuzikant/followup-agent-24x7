"""Grant platform administration (backoffice access) to an existing profile.

    uv run --all-packages python scripts/make_admin.py persona@empresa.com

For Supabase mode: the person signs in and finishes sign-up first, so the profile exists.
In dev mode the seed already makes admin@local.test an administrator.
"""

from __future__ import annotations

import sys

from _cli import ROOT, load_env_file


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("Uso: make_admin.py <email>", file=sys.stderr)
        return 2
    load_env_file(ROOT / ".env")

    from followup_core.identity.application.set_platform_admin import SetPlatformAdmin
    from followup_core.identity.domain.errors import ProfileNotFoundError
    from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
    from inmo24x7_api.database import SessionLocal

    with SessionLocal() as session:
        try:
            profile = SetPlatformAdmin(SqlAlchemyProfileRepository(session)).execute(args[0])
        except ProfileNotFoundError:
            print(f"No hay un perfil con el email {args[0]}. ¿Ya se registró?", file=sys.stderr)
            return 1
        session.commit()
    print(f"{profile.email} ahora es administrador de la plataforma.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
