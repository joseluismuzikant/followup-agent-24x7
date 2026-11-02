class LeadsError(Exception):
    """Base error of the leads context."""


class InvalidLeadTransitionError(LeadsError):
    pass


class LeadNotFoundError(LeadsError):
    pass
