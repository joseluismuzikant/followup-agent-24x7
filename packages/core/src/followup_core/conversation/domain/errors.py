class ConversationError(Exception):
    """Base error for conversation operations."""


class InvalidMessageError(ConversationError):
    """Raised when an inbound message is empty or too long."""


class LlmUnavailableError(ConversationError):
    """Raised when the language model timed out or the provider failed."""


class SimulatorLimitReachedError(ConversationError):
    """Raised when a tenant used up its daily simulator messages."""
