"""What the panel shows for an invoice, derived from its stored status and today's date in
the business's timezone (an invoice due today is not overdue in Buenos Aires at 22:00, even
though it is already tomorrow in UTC)."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from .invoice import PAID_VIA_LABELS, Invoice, InvoiceStatus

# "Por vencer": due within the next 7 days (today included).
DUE_SOON_DAYS = 7


class DisplayKind(StrEnum):
    PAID = "paid"
    OVERDUE = "overdue"
    DUE_SOON = "due_soon"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DisplayStatus:
    kind: DisplayKind
    label: str
    # Only for overdue invoices.
    days_overdue: int | None = None


def today_in(timezone: str, now: datetime) -> date:
    return now.astimezone(ZoneInfo(timezone)).date()


def days_label(days: int) -> str:
    return "1 día" if days == 1 else f"{days} días"


def display_status(invoice: Invoice, today: date) -> DisplayStatus:
    if invoice.status is InvoiceStatus.PAID:
        via = PAID_VIA_LABELS[invoice.paid_via] if invoice.paid_via else None
        return DisplayStatus(DisplayKind.PAID, f"Pagada · {via}" if via else "Pagada")
    if invoice.status is InvoiceStatus.CANCELLED:
        return DisplayStatus(DisplayKind.CANCELLED, "Anulada")
    if invoice.due_date < today:
        days = (today - invoice.due_date).days
        return DisplayStatus(DisplayKind.OVERDUE, f"Vencida · {days_label(days)}", days)
    if invoice.due_date <= today + timedelta(days=DUE_SOON_DAYS):
        return DisplayStatus(DisplayKind.DUE_SOON, "Por vencer")
    return DisplayStatus(DisplayKind.PENDING, "Pendiente")
