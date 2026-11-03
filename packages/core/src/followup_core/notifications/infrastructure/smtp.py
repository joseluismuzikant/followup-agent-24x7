import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid

from ..domain.email import Email, EmailError


@dataclass(frozen=True, slots=True)
class SmtpSettings:
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    starttls: bool = True
    sender: str = "inmo24x7 <avisos@inmo24x7.local>"
    timeout_seconds: float = 10.0


class SmtpEmailSender:
    """Plain SMTP: Mailpit locally (port 1025, no TLS), a provider's relay in production."""

    def __init__(self, settings: SmtpSettings) -> None:
        self._settings = settings

    def send(self, email: Email) -> None:
        settings = self._settings
        message = EmailMessage()
        message["From"] = settings.sender
        message["To"] = ", ".join(email.to)
        message["Subject"] = email.subject
        message["Message-ID"] = make_msgid(
            domain=settings.sender.rpartition("@")[2].strip(">") or None
        )
        message.set_content(email.text)
        if email.html:
            message.add_alternative(email.html, subtype="html")
        try:
            with smtplib.SMTP(
                settings.host, settings.port, timeout=settings.timeout_seconds
            ) as smtp:
                if settings.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.username:
                    smtp.login(settings.username, settings.password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as error:
            raise EmailError(type(error).__name__) from error


@dataclass
class RecordingEmailSender:
    """For tests: keeps what would have been sent."""

    sent: list[Email] = field(default_factory=list)

    def send(self, email: Email) -> None:
        self.sent.append(email)
