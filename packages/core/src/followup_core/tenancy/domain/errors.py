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


class AgentConfigConflictError(TenantError):
    """Raised when another save created the same agent config version first."""


class InvalidOnboardingStepError(TenantError):
    """Raised when onboarding is moved to a step that is not reachable yet."""


class TenantSetupNotFoundError(TenantError):
    """Raised when a tenant has no onboarding or settings record."""


class InvalidSuspensionReasonError(TenantError):
    """Raised when a suspension has no reason or a too long one."""


class TenantSuspendedError(TenantError):
    """Raised when a suspended tenant tries to use the panel."""


class OwnerEmailTakenError(TenantError):
    """Raised when an admin creates a business for an email that already has an account or
    a pending claim."""


class InvalidAuditDetailsError(TenantError):
    """Raised when audit details carry a key outside the allowlist (personal data)."""


class NotInvitedError(TenantError):
    """Raised when someone signs up without an admin's invitation for this product."""
