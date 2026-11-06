"""The invitation email (job `identity.invitation_email`): the link to choose a password and
enter the panel. It never carries the temporary password (the admin shares that apart)."""

import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from followup_core.notifications.domain.email import Email, EmailError, EmailSender
from followup_core.scheduling.domain.jobs import Job, JobError

from ..domain.invitation import INVITATION_TTL

logger = logging.getLogger("followup.identity")


@dataclass(frozen=True, slots=True)
class InvitationEmailData:
    email: str
    business_name: str


InvitationLookup = Callable[[UUID], InvitationEmailData | None]


class SendInvitationEmail:
    def __init__(
        self,
        lookup: InvitationLookup,
        sender: EmailSender,
        product_name: str,
        panel_url: str,
    ) -> None:
        self._lookup = lookup
        self._sender = sender
        self._product_name = product_name
        self._panel_url = panel_url.rstrip("/")

    def __call__(self, job: Job) -> None:
        data = self._lookup(UUID(str(job.payload["invitation_id"])))
        if data is None:
            logger.info("invitation_email_skipped", extra={"job_id": str(job.id)})
            return
        link = f"{self._panel_url}/invitacion?token={job.payload['token']}"
        days = INVITATION_TTL.days
        subject = f"Te invitaron a {self._product_name}: {data.business_name}"
        text = (
            f"Hola,\n\nTe dimos de alta en {self._product_name} como responsable de "
            f"{data.business_name}.\n\nEntrá con este link para elegir tu clave:\n{link}\n\n"
            f"El link vence en {days} días. Si ya tenés una clave de {self._product_name}, "
            "entrá con ella desde el mismo link.\n"
        )
        name = html.escape(data.business_name)
        product = html.escape(self._product_name)
        body = (
            f"<p>Hola,</p><p>Te dimos de alta en {product} como responsable de "
            f"<strong>{name}</strong>.</p>"
            f'<p><a href="{html.escape(link)}">Elegir mi clave y entrar</a></p>'
            f"<p>El link vence en {days} días.</p>"
        )
        try:
            self._sender.send(Email(to=[data.email], subject=subject, text=text, html=body))
        except EmailError as error:
            raise JobError(f"email_{error.code}") from error
