""" "BAJA": setting and lifting a contact's do-not-contact flag, always audited (without
the number). Every path goes through here: the person's own message, the team in the
panel and a platform admin in the backoffice."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from followup_core.tenancy.domain.audit import ActorKind, AuditAction, AuditEvent, AuditLog

from ..domain.opt_out import DoNotContact, DoNotContactRepository, OptOutSource

_ACTORS = {
    OptOutSource.MESSAGE: ActorKind.SYSTEM,
    OptOutSource.TEAM: ActorKind.USER,
    OptOutSource.ADMIN: ActorKind.ADMIN,
}


def _now() -> datetime:
    return datetime.now(UTC)


class ContactOptOut:
    def __init__(
        self,
        contacts: DoNotContactRepository,
        audit: AuditLog,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._contacts = contacts
        self._audit = audit
        self._clock = clock

    def is_blocked(self, tenant_id: UUID, wa_id: str) -> bool:
        return self._contacts.get(tenant_id, wa_id) is not None

    def block(
        self,
        tenant_id: UUID,
        wa_id: str,
        source: OptOutSource,
        *,
        source_message_id: str | None = None,
        profile_id: UUID | None = None,
        confirmation_message_id: UUID | None = None,
        lead_id: UUID | None = None,
    ) -> bool:
        """True when the contact was not blocked before (an existing flag is kept as is)."""
        if self.is_blocked(tenant_id, wa_id):
            return False
        now = self._clock()
        self._contacts.add(
            DoNotContact(
                tenant_id,
                wa_id,
                now,
                source,
                source_message_id,
                profile_id,
                confirmation_message_id,
            )
        )
        self._record(AuditAction.CONTACT_OPTED_OUT, tenant_id, source, profile_id, lead_id, now)
        return True

    def lift(
        self,
        tenant_id: UUID,
        wa_id: str,
        source: OptOutSource,
        *,
        profile_id: UUID | None = None,
        lead_id: UUID | None = None,
    ) -> bool:
        """True when there was a flag. `MESSAGE`: the person wrote again with a new
        inquiry, which counts as contacting the business again."""
        if not self._contacts.remove(tenant_id, wa_id):
            return False
        self._record(
            AuditAction.CONTACT_OPT_OUT_LIFTED,
            tenant_id,
            source,
            profile_id,
            lead_id,
            self._clock(),
        )
        return True

    def _record(
        self,
        action: AuditAction,
        tenant_id: UUID,
        source: OptOutSource,
        profile_id: UUID | None,
        lead_id: UUID | None,
        at: datetime,
    ) -> None:
        details: dict[str, str] = {"source": source.value}
        if lead_id is not None:
            details["lead_id"] = str(lead_id)
        self._audit.record(
            AuditEvent(tenant_id, at, _ACTORS[source], action, details, actor_profile_id=profile_id)
        )
