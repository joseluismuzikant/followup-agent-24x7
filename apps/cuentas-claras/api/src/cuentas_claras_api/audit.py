"""Cuentas Claras's own audit actions (core's audit log stores any product's actions).
Details are ids and counts only: never names, CUITs, amounts or contacts."""

from enum import StrEnum


class CuentasAction(StrEnum):
    CLIENT_CREATED = "client_created"
    CLIENT_UPDATED = "client_updated"
    INVOICE_CREATED = "invoice_created"
    INVOICE_UPDATED = "invoice_updated"
    INVOICE_PAID = "invoice_paid"
    INVOICE_CANCELLED = "invoice_cancelled"
    INVOICES_IMPORTED = "invoices_imported"
    PROMISE_REGISTERED = "promise_registered"
    PROMISE_REMOVED = "promise_removed"
    PROMISE_ENDED = "promise_ended"
    REMINDER_POLICY_SAVED = "reminder_policy_saved"
    TEMPLATE_EDITED = "template_edited"
    TRANSFER_DETAILS_SAVED = "transfer_details_saved"
    REMINDERS_PLANNED_BY_ADMIN = "reminders_planned_by_admin"
