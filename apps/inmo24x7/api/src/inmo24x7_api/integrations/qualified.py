"""A lead as it goes out to Tokko or the webhook (`QualifiedLead`), with its Spanish summary:

"Busca alquiler 2 amb. en Palermo, hasta $900.000, garantía: caución. Pidió visita mié
18/11 09:00. — vía inmo24x7"
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from followup_core.tenancy.domain.business_settings_repository import BusinessSettingsRepository

from ..leads.application.queries import GetLead
from ..leads.conditions import CONDITION_KEYS
from ..leads.display import money
from ..leads.domain.lead import WEB_BUTTON, HandOffReason, Lead, Visit, VisitStatus
from ..leads.domain.sinks import ChosenProperty, QualifiedLead, QualifiedVisit
from ..leads.domain.slots import short_slot_label
from ..properties.domain.property import Operation, Property
from ..properties.domain.repositories import PropertyRepository

SIGNATURE = "— vía inmo24x7"
DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires"

_GUARANTEES: Mapping[str, str] = {
    "propietaria": "propietaria",
    "caucion": "caución",
    "recibo_de_sueldo": "recibo de sueldo",
    "otra": "otra",
    "ninguna": "ninguna",
}


def lead_operation(answers: Mapping[str, Any]) -> str | None:
    value = str(answers.get("operation") or "").lower()
    if value.startswith(("compr", "vent")):
        return Operation.SALE.value
    if value.startswith("alquil"):
        return Operation.RENT.value
    return None


def _rooms(answers: Mapping[str, Any]) -> int | None:
    rooms = answers.get("rooms")
    return rooms if isinstance(rooms, int) and not isinstance(rooms, bool) and rooms > 0 else None


def _budget(answers: Mapping[str, Any]) -> Mapping[str, Any] | None:
    budget = answers.get("budget")
    if isinstance(budget, Mapping) and "amount" in budget and "currency" in budget:
        return {"amount": budget["amount"], "currency": budget["currency"]}
    return None


def summary(
    lead: Lead,
    visit: QualifiedVisit | None,
    chosen: Sequence[ChosenProperty],
) -> str:
    answers = lead.answers
    operation = lead_operation(answers)
    words = {"rent": "alquiler", "sale": "compra"}
    head = f"Busca {words[operation]}" if operation else "Consulta"
    rooms = _rooms(answers)
    if rooms:
        head += " monoambiente" if rooms == 1 else f" {rooms} amb."
    zone = answers.get("zone")
    if isinstance(zone, str) and zone.strip():
        head += f" en {zone.strip()}"
    parts = [head]
    budget = _budget(answers)
    if budget:
        parts.append(f"hasta {money(int(budget['amount']), str(budget['currency']))}")
    guarantee = _GUARANTEES.get(str(answers.get("garantia") or ""))
    if guarantee:
        parts.append(f"garantía: {guarantee}")
    sentences = [", ".join(parts) + "."]
    if visit is not None:
        where = f" en {visit.property_label}" if visit.property_label and not chosen else ""
        sentences.append(f"Pidió visita {visit.label}{where}.")
    if chosen:
        sentences.append("Le interesa: " + "; ".join(item.title for item in chosen) + ".")
    if lead.hand_off_reason is HandOffReason.HUMAN:
        sentences.append("Pidió hablar con alguien del equipo.")
    if lead.source == WEB_BUTTON:
        sentences.append("Llegó por el botón de la web.")
    if lead.do_not_contact:
        sentences.append("Pidió no ser contactado (BAJA): no le escribas por WhatsApp.")
    return " ".join([*sentences, SIGNATURE])


def _contact(lead: Lead) -> tuple[str | None, str | None]:
    """(phone, email): the contact they left, else the WhatsApp number."""
    contact = lead.contact or ""
    email = contact if "@" in contact else None
    phone = contact if contact and email is None else None
    if phone is None and lead.wa_id:
        phone = f"+{lead.wa_id}"
    return phone, email


def _visit(visits: Sequence[Visit], timezone: str) -> QualifiedVisit | None:
    current = [item for item in visits if item.status is not VisitStatus.CANCELLED]
    if not current:
        return None
    item = current[-1]
    start = item.starts_at.astimezone(ZoneInfo(timezone))
    return QualifiedVisit(start, short_slot_label(start), item.property_label, item.status.value)


def _chosen(item: Property) -> ChosenProperty:
    fields = item.fields
    label = money(fields.price, fields.currency.value)
    return ChosenProperty(
        id=item.id,
        title=fields.title,
        address=fields.address,
        operation=fields.operation.value,
        price_label=f"{label} por mes" if fields.operation is Operation.RENT else label,
        link=fields.link,
        source=item.source.value,
        external_id=item.external_id,
        external_ref=item.external_ref,
    )


class BuildQualifiedLead:
    def __init__(
        self,
        get_lead: GetLead,
        properties: PropertyRepository,
        settings: BusinessSettingsRepository,
        panel_url: str,
    ) -> None:
        self._get_lead = get_lead
        self._properties = properties
        self._settings = settings
        self._panel_url = panel_url.rstrip("/")

    def execute(self, tenant_id: UUID, lead_id: UUID) -> QualifiedLead:
        detail = self._get_lead.execute(tenant_id, lead_id)
        lead = detail.lead
        business = self._settings.get(tenant_id)
        timezone = business.timezone if business is not None else DEFAULT_TIMEZONE
        ids = [item.property_id for item in detail.matches if item.chosen]
        visit_ids = [item.property_id for item in detail.visits if item.property_id]
        found: list[ChosenProperty] = []
        for property_id in [*ids, *(i for i in visit_ids if i not in ids)]:
            item = self._properties.get(tenant_id, property_id)
            if item is not None:
                found.append(_chosen(item))
        visit = _visit(detail.visits, timezone)
        phone, email = _contact(lead)
        answers = lead.answers
        return QualifiedLead(
            id=lead.id,
            tenant_id=tenant_id,
            created_at=lead.created_at,
            handed_off_at=lead.handed_off_at,
            hand_off_reason=lead.hand_off_reason.value if lead.hand_off_reason else None,
            name=lead.visitor_name,
            phone=phone,
            email=email,
            operation=lead_operation(answers),
            zone=answers.get("zone") if isinstance(answers.get("zone"), str) else None,
            rooms=_rooms(answers),
            budget=_budget(answers),
            conditions={key: answers[key] for key in sorted(CONDITION_KEYS) if key in answers},
            chosen=found,
            visit=visit,
            summary=summary(lead, visit, found),
            panel_link=f"{self._panel_url}/consultas?lead={lead.id}",
            do_not_contact=lead.do_not_contact,
            source=lead.source,
            channel=lead.channel,
        )


QualifiedLeadBuilder = Callable[[UUID, UUID], QualifiedLead]
