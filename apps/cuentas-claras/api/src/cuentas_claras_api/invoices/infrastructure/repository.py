import re
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, false, func, or_, select
from sqlalchemy.orm import Session

from ...clients.domain.client import name_key
from ...clients.infrastructure.models import ClientModel
from ..domain.invoice import OWED_STATUSES, Currency, Invoice, InvoiceStatus, PaidVia
from ..domain.number import InvoiceType, parse_number_query
from ..domain.repository import (
    Amounts,
    InvoiceListing,
    InvoiceQuery,
    InvoiceRow,
    Summary,
    Tab,
)
from .models import InvoiceModel

OWED = [status.value for status in OWED_STATUSES]


def _to_domain(model: InvoiceModel) -> Invoice:
    return Invoice(
        id=model.id,
        tenant_id=model.tenant_id,
        client_id=model.client_id,
        invoice_type=InvoiceType(model.invoice_type),
        point_of_sale=model.point_of_sale,
        number=model.number,
        issue_date=model.issue_date,
        due_date=model.due_date,
        amount=Decimal(model.amount),
        currency=Currency(model.currency),
        description=model.description,
        status=InvoiceStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        paid_at=model.paid_at,
        paid_via=PaidVia(model.paid_via) if model.paid_via else None,
        payment_reference=model.payment_reference,
        cancelled_reason=model.cancelled_reason,
        promised_until=model.promised_until,
    )


def _apply(model: InvoiceModel, invoice: Invoice) -> None:
    model.client_id = invoice.client_id
    model.invoice_type = invoice.invoice_type.value
    model.point_of_sale = invoice.point_of_sale
    model.number = invoice.number
    model.issue_date = invoice.issue_date
    model.due_date = invoice.due_date
    model.amount = invoice.amount
    model.currency = invoice.currency.value
    model.description = invoice.description
    model.status = invoice.status.value
    model.paid_at = invoice.paid_at
    model.paid_via = invoice.paid_via.value if invoice.paid_via else None
    model.payment_reference = invoice.payment_reference
    model.cancelled_reason = invoice.cancelled_reason
    model.promised_until = invoice.promised_until
    model.updated_at = invoice.updated_at


def _search(q: str) -> ColumnElement[bool] | None:
    """Client name (accents and case folded), CUIT digits, or the invoice number in any of
    the usual formats ("1245", "0003-00001245", "B 3-1245")."""
    q = q.strip()
    if not q:
        return None
    conditions: list[ColumnElement[bool]] = []
    key = name_key(q)
    if key:
        conditions.append(ClientModel.name_key.contains(key))
    digits = re.sub(r"\D", "", q)
    if len(digits) >= 3 and not re.search(r"[a-zA-Z]", q):
        conditions.append(ClientModel.cuit.contains(digits))
    number = parse_number_query(q)
    if number is not None:
        parts = [InvoiceModel.number == number.number]
        if number.point_of_sale is not None:
            parts.append(InvoiceModel.point_of_sale == number.point_of_sale)
        if number.invoice_type is not None:
            parts.append(InvoiceModel.invoice_type == number.invoice_type.value)
        conditions.append(and_(*parts))
    return or_(*conditions) if conditions else false()


class SqlAlchemyInvoiceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _model(self, tenant_id: UUID, invoice_id: UUID) -> InvoiceModel | None:
        model = self._session.get(InvoiceModel, invoice_id)
        return model if model is not None and model.tenant_id == tenant_id else None

    def get(self, tenant_id: UUID, invoice_id: UUID) -> Invoice | None:
        model = self._model(tenant_id, invoice_id)
        return _to_domain(model) if model is not None else None

    def find_by_number(
        self, tenant_id: UUID, invoice_type: InvoiceType, point_of_sale: int, number: int
    ) -> Invoice | None:
        model = self._session.scalar(
            select(InvoiceModel).where(
                InvoiceModel.tenant_id == tenant_id,
                InvoiceModel.invoice_type == invoice_type.value,
                InvoiceModel.point_of_sale == point_of_sale,
                InvoiceModel.number == number,
            )
        )
        return _to_domain(model) if model is not None else None

    def add(self, invoice: Invoice) -> None:
        model = InvoiceModel(
            id=invoice.id, tenant_id=invoice.tenant_id, created_at=invoice.created_at
        )
        _apply(model, invoice)
        self._session.add(model)
        self._session.flush()

    def save(self, invoice: Invoice) -> None:
        model = self._model(invoice.tenant_id, invoice.id)
        if model is None:
            raise LookupError(f"Invoice {invoice.id} does not exist.")
        _apply(model, invoice)
        self._session.flush()

    @staticmethod
    def _tab(tab: Tab, query: InvoiceQuery) -> ColumnElement[bool]:
        is_open = InvoiceModel.status.in_(OWED)
        if tab is Tab.PENDING:
            return is_open
        if tab is Tab.OVERDUE:
            return and_(is_open, InvoiceModel.due_date < query.today)
        if tab is Tab.PROMISED:
            return and_(
                InvoiceModel.status == InvoiceStatus.PROMISED.value,
                InvoiceModel.promised_until >= query.today,
            )
        if tab is Tab.PAID_THIS_MONTH:
            return and_(
                InvoiceModel.status == InvoiceStatus.PAID.value,
                InvoiceModel.paid_at >= query.month_start,
                InvoiceModel.paid_at < query.next_month_start,
            )
        return false()

    def listing(self, tenant_id: UUID, query: InvoiceQuery) -> InvoiceListing:
        base = (
            select(InvoiceModel, ClientModel.name, ClientModel.subtitle)
            .join(ClientModel, ClientModel.id == InvoiceModel.client_id)
            .where(InvoiceModel.tenant_id == tenant_id)
        )
        search = _search(query.q)
        if search is not None:
            base = base.where(search)
        counts = {
            tab: self._session.scalar(
                select(func.count()).select_from(base.where(self._tab(tab, query)).subquery())
            )
            or 0
            for tab in Tab
        }
        order = (
            (InvoiceModel.paid_at.desc(), InvoiceModel.id)
            if query.tab is Tab.PAID_THIS_MONTH
            else (InvoiceModel.due_date, InvoiceModel.point_of_sale, InvoiceModel.number)
        )
        rows = self._session.execute(
            base.where(self._tab(query.tab, query))
            .order_by(*order)
            .offset((query.page - 1) * query.page_size)
            .limit(query.page_size)
        ).all()
        return InvoiceListing(
            rows=[InvoiceRow(_to_domain(row[0]), row.name, row.subtitle) for row in rows],
            total=counts[query.tab],
            counts=counts,
        )

    def for_client(self, tenant_id: UUID, client_id: UUID) -> Sequence[Invoice]:
        models = self._session.scalars(
            select(InvoiceModel)
            .where(InvoiceModel.tenant_id == tenant_id, InvoiceModel.client_id == client_id)
            .order_by(InvoiceModel.due_date.desc(), InvoiceModel.number.desc())
        ).all()
        return [_to_domain(model) for model in models]

    def summary(self, tenant_id: UUID, today: date) -> Summary:
        def amounts(currency: Currency, overdue: bool) -> Amounts:
            conditions = [
                InvoiceModel.tenant_id == tenant_id,
                InvoiceModel.status.in_(OWED),
                InvoiceModel.currency == currency.value,
            ]
            if overdue:
                conditions.append(InvoiceModel.due_date < today)
            row = self._session.execute(
                select(func.coalesce(func.sum(InvoiceModel.amount), 0), func.count()).where(
                    *conditions
                )
            ).one()
            return Amounts(Decimal(row[0]), int(row[1]))

        return Summary(
            to_collect=amounts(Currency.ARS, False),
            overdue=amounts(Currency.ARS, True),
            to_collect_usd=amounts(Currency.USD, False),
            overdue_usd=amounts(Currency.USD, True),
        )

    def has_any(self, tenant_id: UUID) -> bool:
        return bool(
            self._session.scalar(select(exists().where(InvoiceModel.tenant_id == tenant_id)))
        )
