"""The WhatsApp templates of a business (each business has its own, in its own WABA).

The owner writes a template with named fields ("Hola {cliente}, ..."); Meta gets it with
positional variables ({{1}}, {{2}}, ... in order of appearance) and a "Ver y pagar" button
whose URL ends in the payment request's token. Meta's status is kept as Meta writes it
(APPROVED, PENDING, REJECTED, PAUSED, DISABLED, ...): new values must fit.

Editing an approved template submits a new version (Meta limits edits of approved
templates); the newest approved version keeps going out until the new one is approved.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from .policy import TemplateKind

LANGUAGE = "es_AR"
CATEGORY = "UTILITY"
MAX_BODY = 1024
BUTTON_TEXT = "Ver y pagar"
# Meta: a parameter cannot have new lines, tabs or more than 4 spaces in a row.
MAX_PARAMETER = 300
MAX_LISTED_INVOICES = 5


class TemplateError(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field


class Field(StrEnum):
    CLIENT = "cliente"
    BUSINESS = "negocio"
    INVOICE = "factura"  # one number, or the list for several invoices
    AMOUNT = "monto"  # the invoice's amount, or the total
    DUE_DATE = "vencimiento"  # dd/mm; the earliest one for several invoices


_TOKEN = re.compile(r"\{([a-z]+)\}")

DEFAULT_BODIES: dict[TemplateKind, str] = {
    TemplateKind.BEFORE: (
        "Hola {cliente}, te escribimos de {negocio}. Te recordamos que la factura {factura} "
        "por {monto} vence el {vencimiento}. En el botón de abajo tenés el detalle y cómo "
        "pagarla. ¡Gracias!"
    ),
    TemplateKind.DUE: (
        "Hola {cliente}, te escribimos de {negocio}. Hoy vence la factura {factura} por "
        "{monto}. Si ya la pagaste, no hace falta que hagas nada. En el botón de abajo tenés "
        "el detalle y cómo pagarla."
    ),
    TemplateKind.AFTER: (
        "Hola {cliente}, te escribimos de {negocio}. La factura {factura} por {monto} venció "
        "el {vencimiento} y todavía figura impaga. ¿Nos ayudás a regularizarla? En el botón de "
        "abajo tenés el detalle. Si ya la pagaste, respondé este mensaje y lo revisamos."
    ),
    TemplateKind.SEVERAL: (
        "Hola {cliente}, te escribimos de {negocio}. Te recordamos las facturas {factura}, "
        "por un total de {monto}. La primera vence o venció el {vencimiento}. En el botón de "
        "abajo tenés el detalle y cómo pagarlas. Si ya las pagaste, respondé este mensaje y "
        "lo revisamos."
    ),
}

# Meta's template names: lowercase letters, digits and underscores.
_NAME_SLUG = {
    TemplateKind.BEFORE: "antes",
    TemplateKind.DUE: "vence_hoy",
    TemplateKind.AFTER: "vencida",
    TemplateKind.SEVERAL: "varias",
}


class TemplateStatus(StrEnum):
    """Ours before Meta has it; then Meta's own value (kept raw, see `status`)."""

    NOT_SUBMITTED = "NOT_SUBMITTED"  # no WhatsApp connected yet
    SUBMIT_FAILED = "SUBMIT_FAILED"  # Meta refused the request (rejection_reason says why)
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


def fields_in(body: str) -> list[Field]:
    """The named fields, in order of first appearance."""
    seen: list[Field] = []
    for name in _TOKEN.findall(body):
        field = Field(name)
        if field not in seen:
            seen.append(field)
    return seen


def validate_body(body: str) -> str:
    """Trimmed; 1–1024 characters; only known fields, each at most once, never two in a
    row and never at the very start or end (Meta rejects those)."""
    text = "\n".join(line.rstrip() for line in body.strip().splitlines())
    if not text or len(text) > MAX_BODY:
        raise TemplateError("body")
    names = _TOKEN.findall(text)
    if any(name not in Field._value2member_map_ for name in names):
        raise TemplateError("unknown_field")
    if len(names) != len(set(names)):
        raise TemplateError("repeated_field")
    if re.search(r"\{[a-z]+\}\s*\{[a-z]+\}", text):
        raise TemplateError("adjacent_fields")
    if _TOKEN.match(text) or re.search(r"\{[a-z]+\}[.!?¡¿]?$", text):
        raise TemplateError("field_at_edge")
    if "{" in _TOKEN.sub("", text) or "}" in _TOKEN.sub("", text):
        raise TemplateError("braces")
    if "\n\n\n" in text:
        raise TemplateError("body")
    return text


def positional(body: str) -> str:
    """ "Hola {cliente}, ..." → "Hola {{1}}, ..." (Meta's form)."""
    order = {field.value: index for index, field in enumerate(fields_in(body), start=1)}
    return _TOKEN.sub(lambda match: "{{" + str(order[match.group(1)]) + "}}", body)


def template_name(kind: TemplateKind, version: int) -> str:
    return f"cuentas_claras_{_NAME_SLUG[kind]}_v{version}"


def format_amount(amount: Decimal, currency: str = "ARS") -> str:
    """ "$ 1.234,56" (Argentine format), "US$ 1.234,56" for dollars."""
    value = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, cents = f"{value:,.2f}".split(".")
    prefix = "US$" if currency == "USD" else "$"
    return f"{prefix} {whole.replace(',', '.')},{cents}"


def format_due(day: date) -> str:
    return f"{day:%d/%m}"


def clean_parameter(text: str) -> str:
    return " ".join(text.split())[:MAX_PARAMETER]


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    number: str
    amount: Decimal
    currency: str
    due_date: date


def values(client: str, business: str, invoices: Sequence[InvoiceLine]) -> dict[Field, str]:
    """Every field's text for one message (one invoice, or several of one client)."""
    if not invoices:
        raise ValueError("A reminder needs at least one invoice.")
    numbers = [line.number for line in invoices]
    if len(numbers) > MAX_LISTED_INVOICES:
        listed = ", ".join(numbers[:MAX_LISTED_INVOICES])
        number = f"{listed} y {len(numbers) - MAX_LISTED_INVOICES} más"
    else:
        number = ", ".join(numbers)
    totals: dict[str, Decimal] = {}
    for line in invoices:
        totals[line.currency] = totals.get(line.currency, Decimal(0)) + line.amount
    amount = " + ".join(format_amount(total, currency) for currency, total in totals.items())
    return {
        Field.CLIENT: clean_parameter(client),
        Field.BUSINESS: clean_parameter(business),
        Field.INVOICE: clean_parameter(number),
        Field.AMOUNT: amount,
        Field.DUE_DATE: format_due(min(line.due_date for line in invoices)),
    }


def render(body: str, field_values: Mapping[Field, str]) -> str:
    """The text the client reads (C4's preview and the thread's copy of what was sent)."""
    return _TOKEN.sub(lambda match: field_values[Field(match.group(1))], body)


SAMPLE_INVOICES = (
    InvoiceLine("B 0003-00001245", Decimal("180000.00"), "ARS", date(2026, 11, 15)),
    InvoiceLine("B 0003-00001246", Decimal("95500.50"), "ARS", date(2026, 11, 20)),
)


def sample_values(business: str, kind: TemplateKind) -> dict[Field, str]:
    invoices = SAMPLE_INVOICES if kind is TemplateKind.SEVERAL else SAMPLE_INVOICES[:1]
    return values("Edificio Güemes", business or "Tu negocio", invoices)


@dataclass(frozen=True, slots=True)
class WhatsAppTemplate:
    """One version of one of the business's templates."""

    id: UUID
    tenant_id: UUID
    kind: TemplateKind
    version: int
    name: str
    body: str
    status: str
    created_at: datetime
    language: str = LANGUAGE
    category: str = CATEGORY
    meta_template_id: str | None = None
    rejection_reason: str | None = None
    submitted_at: datetime | None = None
    last_synced_at: datetime | None = None

    @classmethod
    def new(
        cls, tenant_id: UUID, kind: TemplateKind, version: int, body: str, now: datetime
    ) -> "WhatsAppTemplate":
        return cls(
            id=uuid4(),
            tenant_id=tenant_id,
            kind=kind,
            version=version,
            name=template_name(kind, version),
            body=validate_body(body),
            status=TemplateStatus.NOT_SUBMITTED.value,
            created_at=now,
        )

    @property
    def approved(self) -> bool:
        return self.status == TemplateStatus.APPROVED.value

    @property
    def submitted(self) -> bool:
        return self.meta_template_id is not None

    def fields(self) -> list[Field]:
        return fields_in(self.body)

    def with_status(
        self, status: str, reason: str | None, now: datetime, meta_id: str | None = None
    ) -> "WhatsAppTemplate":
        return replace(
            self,
            status=status,
            rejection_reason=reason,
            last_synced_at=now,
            meta_template_id=meta_id or self.meta_template_id,
        )

    def meta_request(self, panel_url: str, business: str) -> dict[str, Any]:
        """The POST /{waba_id}/message_templates body."""
        sample = sample_values(business, self.kind)
        base = panel_url.rstrip("/")
        return {
            "name": self.name,
            "language": self.language,
            "category": self.category,
            "components": [
                {
                    "type": "BODY",
                    "text": positional(self.body),
                    "example": {"body_text": [[sample[field] for field in self.fields()]]},
                },
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {
                            "type": "URL",
                            "text": BUTTON_TEXT,
                            "url": f"{base}/p/{{{{1}}}}",
                            "example": [f"{base}/p/ejemplo"],
                        }
                    ],
                },
            ],
        }

    def message_body(self, field_values: Mapping[Field, str], token: str) -> dict[str, Any]:
        """The Cloud API message: the body's parameters in this version's order and the
        button's URL suffix (the payment request's token)."""
        return {
            "type": "template",
            "template": {
                "name": self.name,
                "language": {"code": self.language},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": field_values[field]} for field in self.fields()
                        ],
                    },
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": "0",
                        "parameters": [{"type": "text", "text": token}],
                    },
                ],
            },
        }


def in_use(versions: Sequence[WhatsAppTemplate]) -> WhatsAppTemplate | None:
    """The newest approved version (what reminders send)."""
    approved = [item for item in versions if item.approved]
    return max(approved, key=lambda item: item.version) if approved else None


def newest(versions: Sequence[WhatsAppTemplate]) -> WhatsAppTemplate | None:
    return max(versions, key=lambda item: item.version) if versions else None
