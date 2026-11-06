"""Clients and invoices: CUIT, ARCA numbers, the display status and the transitions."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from cuentas_claras_api.clients.domain.client import Client, ClientFields, name_key
from cuentas_claras_api.clients.domain.cuit import format_cuit, parse_cuit
from cuentas_claras_api.clients.domain.errors import ClientInvalidError, CuitInvalidError
from cuentas_claras_api.invoices.domain.errors import InvoiceAlreadyPaidError, InvoiceInvalidError
from cuentas_claras_api.invoices.domain.invoice import Invoice, InvoiceFields, PaidVia
from cuentas_claras_api.invoices.domain.number import (
    InvoiceType,
    NumberQuery,
    format_number,
    parse_number_query,
)
from cuentas_claras_api.invoices.domain.status import DisplayKind, display_status, today_in

NOW = datetime(2026, 11, 2, 15, tzinfo=UTC)
BA = "America/Argentina/Buenos_Aires"


@pytest.mark.parametrize(
    "value", ["30-71234567-1", "30712345671", "30.71234567.1", " 30 71234567 1 "]
)
def test_a_valid_cuit_in_any_format(value: str) -> None:
    assert parse_cuit(value) == "30712345671"
    assert format_cuit(parse_cuit(value)) == "30-71234567-1"


@pytest.mark.parametrize(
    "value", ["30-71234567-8", "3071234567", "307123456712", "30-7123456A-1", ""]
)
def test_an_invalid_cuit_is_refused(value: str) -> None:
    with pytest.raises(CuitInvalidError):
        parse_cuit(value)


def test_a_client_normalizes_whatsapp_and_flags_a_missing_one() -> None:
    client = Client.create(
        uuid4(), ClientFields(name="  Consorcio  Güemes ", whatsapp="11 5555-0101"), NOW
    )
    assert client.name == "Consorcio Güemes"
    assert client.whatsapp == "+5491155550101"
    assert not client.missing_whatsapp
    assert Client.create(uuid4(), ClientFields(name="Sin número"), NOW).missing_whatsapp
    assert (
        name_key("Edificio  Güemes S.A.") == name_key("edificio guemes sa") == "edificio guemes sa"
    )


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        (ClientFields(name=" "), "name"),
        (ClientFields(name="X", whatsapp="123"), "whatsapp"),
        (ClientFields(name="X", email="no-es-un-email"), "email"),
    ],
)
def test_client_validation(fields: ClientFields, field: str) -> None:
    with pytest.raises(ClientInvalidError) as error:
        Client.create(uuid4(), fields, NOW)
    assert error.value.field == field


def test_arca_numbers_are_padded() -> None:
    assert format_number(InvoiceType.B, 3, 1245) == "B 0003-00001245"
    assert format_number(InvoiceType.A, 12345, 1) == "A 12345-00000001"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1245", NumberQuery(1245)),
        ("0003-00001245", NumberQuery(1245, 3)),
        ("B 3-1245", NumberQuery(1245, 3, InvoiceType.B)),
        ("b0003 00001245", NumberQuery(1245, 3, InvoiceType.B)),
        ("Consorcio", None),
        ("0", None),
    ],
)
def test_invoice_numbers_typed_in_search(text: str, expected: NumberQuery | None) -> None:
    assert parse_number_query(text) == expected


def _invoice(due: date, **changes) -> Invoice:
    fields = InvoiceFields(
        client_id=uuid4(),
        invoice_type=InvoiceType.B,
        point_of_sale=3,
        number=1245,
        issue_date=date(2026, 10, 1),
        due_date=due,
        amount=Decimal("180000.50"),
    )
    return Invoice.create(uuid4(), fields, NOW)


def test_display_status_by_due_date() -> None:
    today = date(2026, 11, 2)
    overdue = display_status(_invoice(date(2026, 10, 21)), today)
    assert (overdue.kind, overdue.label, overdue.days_overdue) == (
        DisplayKind.OVERDUE,
        "Vencida · 12 días",
        12,
    )
    assert display_status(_invoice(date(2026, 11, 1)), today).label == "Vencida · 1 día"
    # "Por vencer": today through 7 days ahead.
    assert display_status(_invoice(today), today).kind is DisplayKind.DUE_SOON
    assert display_status(_invoice(date(2026, 11, 9)), today).kind is DisplayKind.DUE_SOON
    assert display_status(_invoice(date(2026, 11, 10)), today).label == "Pendiente"


def test_today_is_the_business_day_not_the_server_day() -> None:
    # 22:30 on 2 November in Buenos Aires is already 3 November in UTC.
    late = datetime(2026, 11, 3, 1, 30, tzinfo=UTC)
    today = today_in(BA, late)
    assert today == date(2026, 11, 2)
    assert display_status(_invoice(date(2026, 11, 2)), today).kind is DisplayKind.DUE_SOON
    assert today_in("UTC", late) == date(2026, 11, 3)


def test_paying_and_cancelling() -> None:
    invoice = _invoice(date(2026, 11, 10))
    paid = invoice.mark_paid(date(2026, 11, 1), PaidVia.MERCADO_PAGO, " op 123 ", NOW)
    assert display_status(paid, date(2026, 11, 2)).label == "Pagada · Mercado Pago"
    assert paid.payment_reference == "op 123"
    with pytest.raises(InvoiceAlreadyPaidError):
        paid.mark_paid(date(2026, 11, 1), PaidVia.MANUAL, None, NOW)
    with pytest.raises(InvoiceAlreadyPaidError):
        paid.cancel("error", NOW)
    with pytest.raises(InvoiceInvalidError):
        invoice.mark_paid(date(2026, 11, 3), PaidVia.MANUAL, None, NOW)  # in the future

    cancelled = invoice.cancel("  Se facturó dos veces ", NOW)
    assert cancelled.cancelled_reason == "Se facturó dos veces"
    assert display_status(cancelled, date(2026, 11, 2)).label == "Anulada"
    with pytest.raises(InvoiceInvalidError):
        cancelled.mark_paid(date(2026, 11, 1), PaidVia.MANUAL, None, NOW)
    with pytest.raises(InvoiceInvalidError):
        invoice.cancel("   ", NOW)


@pytest.mark.parametrize("amount", ["0", "-5", "12.345", "NaN"])
def test_amounts_are_positive_with_two_decimals(amount: str) -> None:
    with pytest.raises(InvoiceInvalidError):
        _invoice_with_amount(Decimal(amount))


def _invoice_with_amount(amount: Decimal) -> Invoice:
    fields = InvoiceFields(
        client_id=uuid4(),
        invoice_type=InvoiceType.B,
        point_of_sale=3,
        number=1,
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 1),
        amount=amount,
    )
    return Invoice.create(uuid4(), fields, NOW)
