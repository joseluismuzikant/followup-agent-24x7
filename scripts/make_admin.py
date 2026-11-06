"""Grant platform administration (backoffice access) in one product.

    uv run --all-packages python scripts/make_admin.py persona@empresa.com
    uv run --all-packages python scripts/make_admin.py persona@empresa.com --product cuentas-claras
    uv run --all-packages python scripts/make_admin.py persona@empresa.com --create

A person has one profile per product, so admin access is per product (inmo24x7 by default).
Without --create the profile must exist (the person was invited and came in). --create is
for the first admin, who nobody can invite: it creates the "Plataforma" business, the profile
and, when the person has no account yet, the account with a temporary password printed once
(they change it on their first sign-in). In dev mode the seed already makes admin@local.test
an administrator of both backoffices.
"""

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from datetime import UTC, datetime

from _cli import ROOT, load_env_file

PRODUCTS = {"inmo24x7": "inmo24x7", "cuentas-claras": "cuentas_claras"}
PLATFORM_BUSINESS = "Plataforma"
PLATFORM_TYPE = {"inmo24x7": "inmobiliaria", "cuentas-claras": "otro"}


def create_admin(session, product_key: str, email: str) -> str | None:  # noqa: ANN001
    """The admin's account, "Plataforma" business and profile. The temporary password, or
    None when the account already existed."""
    from followup_core.identity.domain.account import Account, temporary_password
    from followup_core.identity.infrastructure.accounts import SqlAlchemyAccountRepository
    from followup_platform.identity import build_account_directory
    from inmo24x7_api.config import get_settings

    if product_key == "inmo24x7":
        import inmo24x7_api.container as container
    else:
        import cuentas_claras_api.container as container
    from followup_core.tenancy.domain.errors import OwnerEmailTakenError

    accounts = SqlAlchemyAccountRepository(session)
    password: str | None = None
    account = accounts.get_by_email(email)
    if account is None:
        password = temporary_password()
        user_id = build_account_directory(get_settings(), session).create_user(email, password)
        accounts.add(Account(user_id, email, True, datetime.now(UTC)))
    else:
        user_id = account.user_id
    # The business or the profile already exists: sign-up below returns it.
    with suppress(OwnerEmailTakenError):
        container.create_business_use_case(session).execute(
            user_id, PLATFORM_BUSINESS, PLATFORM_TYPE[product_key], email
        )
    container.sign_up_use_case(session).execute(user_id, email)
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Make a profile a platform administrator.")
    parser.add_argument("email")
    parser.add_argument("--product", choices=sorted(PRODUCTS), default="inmo24x7")
    parser.add_argument(
        "--create",
        action="store_true",
        help="create the account, the Plataforma business and the profile if missing",
    )
    args = parser.parse_args(argv)
    load_env_file(ROOT / ".env")

    from followup_core.identity.application.set_platform_admin import SetPlatformAdmin
    from followup_core.identity.domain.errors import ProfileNotFoundError
    from followup_core.identity.infrastructure.repository import SqlAlchemyProfileRepository
    from followup_core.tenancy.domain.product import Product
    from inmo24x7_api.database import SessionLocal

    email = args.email.strip().lower()
    product = Product(PRODUCTS[args.product])
    password: str | None = None
    with SessionLocal() as session:
        if args.create:
            password = create_admin(session, args.product, email)
        try:
            profile = SetPlatformAdmin(SqlAlchemyProfileRepository(session, product)).execute(email)
        except ProfileNotFoundError:
            print(
                f"No hay un perfil de {args.product} con el email {email}. "
                "Invitalo desde el backoffice o usá --create.",
                file=sys.stderr,
            )
            return 1
        session.commit()
    print(f"{profile.email} ahora es administrador de {args.product}.")
    if password:
        print(f"Clave temporal (se muestra una sola vez; la cambia al entrar): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
