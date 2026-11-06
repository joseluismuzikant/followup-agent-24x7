class ClientsError(Exception):
    """Base error of the Clients context."""


class ClientNotFoundError(ClientsError):
    pass


class ClientInvalidError(ClientsError):
    """A field is missing or malformed; `field` says which."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class CuitInvalidError(ClientsError):
    pass


class CuitTakenError(ClientsError):
    """Another client of the business already has this CUIT."""
