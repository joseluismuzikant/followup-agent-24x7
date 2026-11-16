"""The team's say over the agent's evaluation of a lead's conditions ("Cumple igual")."""

from uuid import UUID

from followup_core.conversation.application.threads import Clock, utc_now
from followup_core.tenancy.domain.audit import ActorKind, AuditEvent, AuditLog

from ...audit import InmoAction
from ..domain.errors import LeadNotFoundError, MatchNotFoundError
from ..domain.repositories import LeadRepository


class OverrideMatch:
    def __init__(self, leads: LeadRepository, audit: AuditLog, clock: Clock = utc_now) -> None:
        self._leads = leads
        self._audit = audit
        self._clock = clock

    def execute(
        self,
        tenant_id: UUID,
        profile_id: UUID,
        lead_id: UUID,
        property_id: UUID,
        status: str | None,
    ) -> str | None:
        """The lead's overall status after the change."""
        if self._leads.get(tenant_id, lead_id) is None:
            raise LeadNotFoundError(str(lead_id))
        now = self._clock()
        if not self._leads.override_match(lead_id, property_id, status, profile_id, now):
            raise MatchNotFoundError(str(property_id))
        overall = self._leads.refresh_conditions_status(lead_id)
        self._audit.record(
            AuditEvent(
                tenant_id,
                now,
                ActorKind.USER,
                InmoAction.CONDITION_MATCH_OVERRIDDEN,
                {
                    "lead_id": str(lead_id),
                    "property_id": str(property_id),
                    "status": status or "agent",
                },
                actor_profile_id=profile_id,
            )
        )
        return overall
