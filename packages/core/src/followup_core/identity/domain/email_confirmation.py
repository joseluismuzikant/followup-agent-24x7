from typing import Protocol


class EmailConfirmation(Protocol):
    """Whether the auth provider has confirmed the email of the person behind this token.
    Joining a business an admin created for an email ("Dar de alta") needs that proof."""

    def is_confirmed(self, access_token: str, email: str) -> bool:
        """False on any doubt (unconfirmed, another email, the provider unreachable)."""
        ...
