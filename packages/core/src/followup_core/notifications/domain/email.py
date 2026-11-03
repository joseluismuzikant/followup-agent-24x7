from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Email:
    to: Sequence[str]
    subject: str
    text: str
    html: str | None = None


class EmailSender(Protocol):
    def send(self, email: Email) -> None:
        """Raises EmailError when the message could not be handed to the server."""
        ...


class EmailError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
