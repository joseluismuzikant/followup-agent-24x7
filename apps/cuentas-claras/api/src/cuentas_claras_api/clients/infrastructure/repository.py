import re
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Row, func, or_, select
from sqlalchemy.orm import Session

from ...invoices.infrastructure.models import InvoiceModel
from ..domain.client import Client, name_key
from ..domain.repository import ClientBalance, ClientPage
from .models import ClientModel


def _to_domain(model: ClientModel) -> Client:
    return Client(
        id=model.id,
        tenant_id=model.tenant_id,
        name=model.name,
        subtitle=model.subtitle,
        cuit=model.cuit,
        contact_name=model.contact_name,
        whatsapp=model.whatsapp,
        email=model.email,
        notes=model.notes,
        active=model.active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _apply(model: ClientModel, client: Client) -> None:
    model.name = client.name
    model.name_key = client.name_key
    model.subtitle = client.subtitle
    model.cuit = client.cuit
    model.contact_name = client.contact_name
    model.whatsapp = client.whatsapp
    model.email = client.email
    model.notes = client.notes
    model.active = client.active
    model.updated_at = client.updated_at


class SqlAlchemyClientRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _model(self, tenant_id: UUID, client_id: UUID) -> ClientModel | None:
        model = self._session.get(ClientModel, client_id)
        return model if model is not None and model.tenant_id == tenant_id else None

    def get(self, tenant_id: UUID, client_id: UUID) -> Client | None:
        model = self._model(tenant_id, client_id)
        return _to_domain(model) if model is not None else None

    def find_by_cuit(self, tenant_id: UUID, cuit: str) -> Client | None:
        model = self._session.scalar(
            select(ClientModel).where(ClientModel.tenant_id == tenant_id, ClientModel.cuit == cuit)
        )
        return _to_domain(model) if model is not None else None

    def find_by_name_key(self, tenant_id: UUID, name_key: str) -> Client | None:
        model = self._session.scalar(
            select(ClientModel)
            .where(ClientModel.tenant_id == tenant_id, ClientModel.name_key == name_key)
            .order_by(ClientModel.created_at)
            .limit(1)
        )
        return _to_domain(model) if model is not None else None

    def add(self, client: Client) -> None:
        model = ClientModel(id=client.id, tenant_id=client.tenant_id, created_at=client.created_at)
        _apply(model, client)
        self._session.add(model)
        self._session.flush()

    def save(self, client: Client) -> None:
        model = self._model(client.tenant_id, client.id)
        if model is None:
            raise LookupError(f"Client {client.id} does not exist.")
        _apply(model, client)
        self._session.flush()

    def _balances(self, tenant_id: UUID):  # noqa: ANN202 - a select, typed by its columns
        open_rows = (
            select(
                InvoiceModel.client_id,
                func.count().label("open_invoices"),
                func.coalesce(
                    func.sum(InvoiceModel.amount).filter(InvoiceModel.currency == "ARS"), 0
                ).label("owed_ars"),
                func.coalesce(
                    func.sum(InvoiceModel.amount).filter(InvoiceModel.currency == "USD"), 0
                ).label("owed_usd"),
            )
            .where(InvoiceModel.tenant_id == tenant_id, InvoiceModel.status == "open")
            .group_by(InvoiceModel.client_id)
            .subquery()
        )
        return (
            select(
                ClientModel,
                func.coalesce(open_rows.c.open_invoices, 0).label("open_invoices"),
                func.coalesce(open_rows.c.owed_ars, 0).label("owed_ars"),
                func.coalesce(open_rows.c.owed_usd, 0).label("owed_usd"),
            )
            .outerjoin(open_rows, open_rows.c.client_id == ClientModel.id)
            .where(ClientModel.tenant_id == tenant_id)
        )

    @staticmethod
    def _balance(row: Row) -> ClientBalance:
        return ClientBalance(
            client=_to_domain(row[0]),
            open_invoices=int(row.open_invoices),
            owed_ars=Decimal(row.owed_ars),
            owed_usd=Decimal(row.owed_usd),
        )

    def search(
        self, tenant_id: UUID, q: str, missing_whatsapp: bool, page: int, page_size: int
    ) -> ClientPage:
        statement = self._balances(tenant_id)
        key = name_key(q)
        digits = re.sub(r"\D", "", q)
        conditions = []
        if key:
            conditions.append(ClientModel.name_key.contains(key))
        if len(digits) >= 3:
            conditions.append(ClientModel.cuit.contains(digits))
        if conditions:
            statement = statement.where(or_(*conditions))
        if missing_whatsapp:
            statement = statement.where(ClientModel.whatsapp.is_(None))
        total = self._session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self._session.execute(
            statement.order_by(ClientModel.name_key, ClientModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return ClientPage([self._balance(row) for row in rows], total, page, page_size)

    def balance(self, tenant_id: UUID, client_id: UUID) -> ClientBalance | None:
        row = self._session.execute(
            self._balances(tenant_id).where(ClientModel.id == client_id)
        ).one_or_none()
        return self._balance(row) if row is not None else None
