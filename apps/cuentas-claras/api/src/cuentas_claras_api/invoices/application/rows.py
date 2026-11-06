"""One spreadsheet row of the invoice template, read the way an Argentine business writes
it: dd/mm/aaaa dates, "180.000,50" amounts, CUITs with or without dashes. Every problem is a
Spanish message naming the row."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from ...clients.domain.client import ClientFields, validate_fields
from ...clients.domain.errors import ClientInvalidError, CuitInvalidError
from ..domain.invoice import Currency, PaidVia
from ..domain.number import MAX_NUMBER, MAX_POINT_OF_SALE, InvoiceType


class RowError(ValueError):
    """`message` completes "Fila N: …"."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
# XLSX date cells arrive as ISO text ("2026-10-10" or "2026-10-10T00:00:00").
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ]00:00:00)?$")
_THOUSANDS = re.compile(r"^\d{1,3}(\.\d{3})+$")

CLIENT_FIELD_ERRORS = {
    "name": "el nombre del cliente es muy largo.",
    "subtitle": "el detalle del cliente es muy largo.",
    "contact_name": "el contacto es muy largo.",
    "whatsapp": "el WhatsApp no es un número válido.",
    "email": "el email no es válido.",
}

PAID_VIA = {
    "": PaidVia.MANUAL,
    "manual": PaidVia.MANUAL,
    "efectivo": PaidVia.MANUAL,
    "transferencia": PaidVia.TRANSFER,
    "mercado pago": PaidVia.MERCADO_PAGO,
    "mercadopago": PaidVia.MERCADO_PAGO,
    "mercado_pago": PaidVia.MERCADO_PAGO,
    "otro": PaidVia.OTHER,
}


def parse_date(text: str) -> date:
    text = text.strip()
    match = _DMY.fullmatch(text)
    try:
        if match:
            day, month, year = (int(part) for part in match.groups())
            return date(year, month, day)
        match = _ISO.fullmatch(text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            return date(year, month, day)
    except ValueError:
        pass
    raise RowError("la fecha tiene que ser dd/mm/aaaa.")


def parse_amount(text: str) -> Decimal:
    """ "180.000,50", "$ 180.000", "180000", "180000.5" (an XLSX number cell)."""
    cleaned = text.replace("$", "").replace("ARS", "").replace("USD", "").replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif _THOUSANDS.fullmatch(cleaned):
        cleaned = cleaned.replace(".", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as error:
        raise RowError("el monto no es un número.") from error
    if not amount.is_finite():
        raise RowError("el monto no es un número.")
    if amount <= 0:
        raise RowError("el monto tiene que ser mayor a cero.")
    if amount != amount.quantize(Decimal("0.01")):
        raise RowError("el monto puede tener hasta 2 decimales.")
    return amount.quantize(Decimal("0.01"))


def _integer(text: str, limit: int, message: str) -> int:
    digits = text.strip().lstrip("0") or "0"
    if not digits.isdigit() or not 1 <= int(digits) <= limit:
        raise RowError(message)
    return int(digits)


@dataclass(frozen=True, slots=True)
class InvoiceRow:
    client: ClientFields
    invoice_type: InvoiceType
    point_of_sale: int
    number: int
    issue_date: date
    due_date: date
    amount: Decimal
    currency: Currency
    description: str
    paid: bool
    paid_at: date | None
    paid_via: PaidVia | None


def read_row(values: dict[str, str], today: date) -> InvoiceRow:
    """Validated in the template's column order, so each row reports its first problem."""

    def cell(name: str) -> str:
        return values.get(name, "").strip()

    if not cell("cliente"):
        raise RowError("falta el cliente.")
    client = ClientFields(
        name=cell("cliente"),
        subtitle=cell("detalle_cliente"),
        cuit=cell("cuit"),
        contact_name=cell("contacto"),
        whatsapp=cell("whatsapp"),
        email=cell("email"),
    )
    try:
        validate_fields(client)
    except CuitInvalidError as error:
        raise RowError("el CUIT no es válido.") from error
    except ClientInvalidError as error:
        raise RowError(
            CLIENT_FIELD_ERRORS.get(error.field, "los datos del cliente no son válidos.")
        ) from error
    kind = cell("tipo").upper()
    if kind not in InvoiceType.__members__:
        raise RowError("el tipo tiene que ser A, B o C.")
    point_of_sale = _integer(
        cell("punto_venta"), MAX_POINT_OF_SALE, "el punto de venta no es válido."
    )
    number = _integer(cell("numero"), MAX_NUMBER, "el número de factura no es válido.")
    if not cell("vencimiento"):
        raise RowError("falta el vencimiento.")
    due_date = parse_date(cell("vencimiento"))
    issue_date = parse_date(cell("fecha_emision")) if cell("fecha_emision") else due_date
    if due_date < issue_date:
        raise RowError("el vencimiento es anterior a la fecha de emisión.")
    if not cell("monto"):
        raise RowError("falta el monto.")
    amount = parse_amount(cell("monto"))
    currency_text = cell("moneda").upper() or Currency.ARS.value
    if currency_text not in Currency.__members__:
        raise RowError("la moneda tiene que ser ARS o USD.")
    state = cell("estado").lower() or "pendiente"
    if state not in ("pendiente", "pagada"):
        raise RowError("el estado tiene que ser pendiente o pagada.")
    paid = state == "pagada"
    paid_at = paid_via = None
    if paid:
        paid_at = parse_date(cell("fecha_pago")) if cell("fecha_pago") else due_date
        if paid_at > today:
            raise RowError("la fecha de pago todavía no llegó.")
        via = cell("medio_pago").lower()
        if via not in PAID_VIA:
            raise RowError("el medio de pago no es válido.")
        paid_via = PAID_VIA[via]
    return InvoiceRow(
        client=client,
        invoice_type=InvoiceType(kind),
        point_of_sale=point_of_sale,
        number=number,
        issue_date=issue_date,
        due_date=due_date,
        amount=amount,
        currency=Currency(currency_text),
        description=cell("descripcion"),
        paid=paid,
        paid_at=paid_at,
        paid_via=paid_via,
    )
