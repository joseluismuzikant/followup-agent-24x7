class InvoicesError(Exception):
    """Base error of the Invoices context."""


class InvoiceNotFoundError(InvoicesError):
    pass


class InvoiceInvalidError(InvoicesError):
    """A field is missing or malformed; `field` says which."""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class InvoiceNumberTakenError(InvoicesError):
    """The business already has an invoice with this type, point of sale and number."""


class InvoiceAlreadyPaidError(InvoicesError):
    pass


class ImportFileInvalidError(InvoicesError):
    pass


class ImportTooLargeError(InvoicesError):
    pass


class ImportNotFoundError(InvoicesError):
    pass
