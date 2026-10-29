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


class InvalidBusinessTypeError(TenantError):
    """Raised when a business type is not one of the supported values."""


class InvalidTeamHoursError(TenantError):
    """Raised when the weekly team schedule is malformed."""


class InvalidNotificationEmailError(TenantError):
    """Raised when notification emails are missing, invalid, or too many."""


class InvalidAgentNameError(TenantError):
    """Raised when an agent name cannot be used."""


class InvalidQuestionsError(TenantError):
    """Raised when the qualification questions are malformed."""


class InvalidOnboardingStepError(TenantError):
    """Raised when onboarding is moved to a step that is not reachable yet."""


class TenantSetupNotFoundError(TenantError):
    """Raised when a tenant has no onboarding or settings record."""
