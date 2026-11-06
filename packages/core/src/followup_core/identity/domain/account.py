"""A person's account: one per email, shared by every product (a profile is per product).
Accounts are only created by an admin's invitation; a new one starts with a temporary
password that must be changed before anything else."""

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from .errors import WeakPasswordError

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 72  # bcrypt's limit, which Supabase Auth uses
# No look-alike characters (0/O, 1/l/I): the admin reads it out or pastes it into a chat.
_TEMPORARY_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TEMPORARY_PASSWORD_LENGTH = 12


@dataclass(frozen=True, slots=True)
class Account:
    user_id: UUID
    email: str
    must_change_password: bool
    created_at: datetime
    password_changed_at: datetime | None = None


def check_password(password: str, email: str) -> None:
    """Raises WeakPasswordError with a code the panel shows in Spanish."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError("password_too_short")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError("password_too_long")
    if password.strip().lower() == email.strip().lower():
        raise WeakPasswordError("password_is_email")


def temporary_password() -> str:
    return "".join(secrets.choice(_TEMPORARY_ALPHABET) for _ in range(TEMPORARY_PASSWORD_LENGTH))


class AccountRepository(Protocol):
    def get(self, user_id: UUID) -> Account | None: ...

    def get_by_email(self, email: str) -> Account | None: ...

    def add(self, account: Account) -> None: ...

    def set_must_change(self, user_id: UUID, value: bool, at: datetime | None = None) -> None:
        """`at` is when the password was changed (only when clearing the flag)."""
        ...


class AccountDirectory(Protocol):
    """The auth provider's users: Supabase Auth in production, a local table in dev mode."""

    def create_user(self, email: str, password: str) -> UUID:
        """The new user's id. Raises AccountConflictError when the provider already has
        this email (a user this platform did not create)."""
        ...

    def set_password(self, user_id: UUID, email: str, password: str) -> None: ...
