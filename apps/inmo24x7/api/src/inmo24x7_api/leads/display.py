"""Server-side formatting for the "Lo que el agente ya sabe" panel and property cards."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from followup_core.tenancy.domain.agent_config import AgentConfig, QuestionKind

from .properties import Property


@dataclass(frozen=True, slots=True)
class KnownRow:
    key: str
    label: str
    value: str | None


def thousands(amount: int) -> str:
    return f"{amount:,}".replace(",", ".")


def money(amount: int, currency: str) -> str:
    return f"USD {thousands(amount)}" if currency == "USD" else f"${thousands(amount)}"


def price_label(item: Property) -> str:
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
