class LeadsError(Exception):
    """Base error of the leads context."""


class InvalidLeadTransitionError(LeadsError):
    pass


class LeadNotFoundError(LeadsError):
    pass


class VisitNotFoundError(LeadsError):
    pass


class VisitCancelledError(LeadsError):
    pass


class VisitTimeInPastError(LeadsError):
    pass


class OutsideServiceWindowError(LeadsError):
    """More than 24 hours since the lead's last WhatsApp message: only a template can go."""


class TemplateNotConfiguredError(LeadsError):
    """The WhatsApp connection has no visit confirmation template."""
