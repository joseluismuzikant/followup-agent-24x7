class TenantError(Exception):
    """Base error for tenant operations."""


class InvalidTenantNameError(TenantError):
    """Raised when a tenant name cannot be used."""


class InvalidTenantSlugError(TenantError):
    """Raised when a tenant slug has an invalid format."""


class DuplicateTenantSlugError(TenantError):
    """Raised when a tenant slug is already taken."""


class TenantNotFoundError(TenantError):
    """Raised when a tenant does not exist."""
