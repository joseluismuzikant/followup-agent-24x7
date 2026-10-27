class IdentityError(Exception):
    """Base error for identity operations."""


class ProfileNotFoundError(IdentityError):
    """Raised when a profile does not exist for an authenticated user."""


class InvalidTokenError(IdentityError):
    """Raised when an access token cannot be verified."""
