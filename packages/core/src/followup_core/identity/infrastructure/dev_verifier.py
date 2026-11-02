import re
from uuid import UUID, uuid5

from ..domain.errors import InvalidTokenError
from ..domain.token_verifier import VerifiedToken

# Fixed so the same email always maps to the same user, across restarts and machines.
DEV_NAMESPACE = UUID("6f1d3c52-6b8e-4c8a-9d7e-2f4b8a1c0e93")
DEV_TOKEN_PREFIX = "dev:"
_EMAIL = re.compile(r"^[^@\s:]+@[^@\s:]+\.[^@\s:]+$")


def dev_user_id(email: str) -> UUID:
    return uuid5(DEV_NAMESPACE, email.strip().lower())


class DevTokenVerifier:
    """Local development only: accepts `dev:<email>` and nothing else.

    The settings refuse this mode when APP_ENV=production.
    """

    def verify(self, token: str) -> VerifiedToken:
        if not token.startswith(DEV_TOKEN_PREFIX):
            raise InvalidTokenError("Not a development token.")
        email = token.removeprefix(DEV_TOKEN_PREFIX).strip().lower()
        if not _EMAIL.fullmatch(email):
            raise InvalidTokenError("Development token without a valid email.")
        return VerifiedToken(user_id=dev_user_id(email), email=email)
