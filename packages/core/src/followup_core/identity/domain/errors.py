class IdentityError(Exception):
    """Base error for identity operations."""


class ProfileNotFoundError(IdentityError):
    """Raised when a profile does not exist for an authenticated user."""


class InvalidTokenError(IdentityError):
    """Raised when an access token cannot be verified."""


class WeakPasswordError(IdentityError):
    """Raised when a new password breaks the rules; the message is the error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AccountConflictError(IdentityError):
    """Raised when the auth provider already has a user with this email that the platform
    did not create."""


class AccountNotFoundError(IdentityError):
    """Raised when an account the operation needs does not exist."""


class InvitationNotFoundError(IdentityError):
    """Raised when an invitation token is unknown."""


class InvitationExpiredError(IdentityError):
    """Raised when an invitation is past its expiry or replaced by a newer one."""


class InvitationUsedError(IdentityError):
    """Raised when an invitation was already accepted."""


class OwnerAlreadyJoinedError(IdentityError):
    """Raised when an invitation is resent (or a temporary password reset) for a business
    whose owner already signed in."""
