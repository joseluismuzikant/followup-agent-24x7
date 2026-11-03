"""Server-side formatting for the "Lo que el agente ya sabe" panel and property cards."""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from followup_core.tenancy.domain.agent_config import AgentConfig, QuestionKind

from ..properties.domain.search import Listing
from .domain.lead import LeadStatus, VisitStatus

if TYPE_CHECKING:
    from .application.queries import LeadExport

STATUS_LABELS: Mapping[LeadStatus, str] = {
    LeadStatus.QUALIFYING: "Calificando",
    LeadStatus.VISIT_PROPOSED: "Visita propuesta",
    LeadStatus.HUMAN_REQUESTED: "Pidió hablar con alguien",
    LeadStatus.VISIT_CONFIRMED: "Visita confirmada",
}
VISIT_STATUS_LABELS: Mapping[VisitStatus, str] = {
    VisitStatus.PROPOSED: "Propuesta",
    VisitStatus.CONFIRMED: "Confirmada",
    VisitStatus.CANCELLED: "Cancelada",
}
CHANNEL_LABELS = {"whatsapp": "WhatsApp", "simulator": "Simulador"}


@dataclass(frozen=True, slots=True)
class KnownRow:
    key: str
    label: str
    value: str | None


def thousands(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


def money(amount: int, currency: str) -> str:
    return f"USD {thousands(amount)}" if currency == "USD" else f"${thousands(amount)}"


def price_label(item: Listing) -> str:
    label = money(item.price, item.currency)
    return f"{label} por mes" if item.operation == "rent" else label


def _answer(kind: QuestionKind, value: Any) -> str | None:
    if value is None:
        return None
    match kind:
        case QuestionKind.CHOICE:
            return str(value)[:1].upper() + str(value)[1:]
        case QuestionKind.MONEY:
            # As in S3: "Hasta $900.000" for rent budgets in pesos, "USD 120.000" for sales.
            label = money(value["amount"], value["currency"])
            return label if value["currency"] == "USD" else f"Hasta {label}"
        case QuestionKind.BOOLEAN:
            return "Sí" if value else "No"
        case QuestionKind.NUMBER | QuestionKind.TEXT:
            return str(value)


def known_rows(config: AgentConfig, state: Mapping[str, Any]) -> list[KnownRow]:
    """One row per enabled question in config order, then name and contact.

    Answers for keys outside the pinned config are not shown.
    """
    answers: Mapping[str, Any] = state.get("answers") or {}
    rows = [
        KnownRow(question.key, question.label, _answer(question.kind, answers.get(question.key)))
        for question in config.qualification_questions
        if question.enabled
    ]
    rows.append(KnownRow("visitor_name", "Nombre", state.get("visitor_name")))
    rows.append(KnownRow("contact", "Contacto", state.get("contact")))
    return rows


def looking_for(answers: Mapping[str, Any]) -> str:
    """One line for the leads list: "Alquiler · 2 amb. · Palermo · hasta $900.000"."""
    parts: list[str] = []
    operation = answers.get("operation")
    if operation:
        parts.append(str(operation)[:1].upper() + str(operation)[1:])
    rooms = answers.get("rooms")
    if isinstance(rooms, int):
        parts.append(f"{rooms} amb.")
    zone = answers.get("zone")
    if zone:
        parts.append(str(zone))
    budget = answers.get("budget")
    if isinstance(budget, Mapping) and "amount" in budget and "currency" in budget:
        parts.append(f"hasta {money(budget['amount'], budget['currency'])}")
    return " · ".join(parts)


def lead_csv(export: "LeadExport") -> Iterator[list[str]]:
    """The "Exportar CSV" rows: a header, then one row per lead. One column per question the
    business asks today (its label as header), in config order."""
    zone = ZoneInfo(export.timezone)
    questions = [q for q in export.agent_config.qualification_questions if q.enabled]

    def when(value: datetime) -> str:
        return f"{value.astimezone(zone):%d/%m/%Y %H:%M}"

    yield [
        "Fecha de alta",
        "Nombre",
        "Teléfono",
        "Canal",
        "Estado",
        *[question.label for question in questions],
        "Visita (fecha y propiedad)",
        "Estado de la visita",
        "Última actividad",
    ]
    for lead in export.leads:
        visit = export.latest_visits.get(lead.id)
        yield [
            when(lead.created_at),
            lead.visitor_name or "",
            lead.contact or "",
            CHANNEL_LABELS.get(lead.channel, lead.channel),
            STATUS_LABELS[lead.status],
            *[_answer(q.kind, lead.answers.get(q.key)) or "" for q in questions],
            f"{when(visit.starts_at)} · {visit.property_label}" if visit else "",
            VISIT_STATUS_LABELS[visit.status] if visit else "",
            when(lead.last_activity_at),
        ]
