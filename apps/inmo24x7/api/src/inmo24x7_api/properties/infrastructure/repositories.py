from collections.abc import Sequence
from uuid import UUID

from followup_core.conversation.domain.answers import normalize
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from ...leads.infrastructure.models import LeadModel, LeadPropertyMatchModel
from ..domain.imports import FailedRow, PropertyImport
from ..domain.property import Currency, Operation, Property, PropertyFields, PropertyStatus
from ..domain.repositories import PropertyFilters, PropertyPage, PropertyRow
from ..domain.search import Listing, PropertyMatch, PropertyQuery, rank
from .models import PropertyImportModel, PropertyModel
from .sample import SAMPLE_LISTINGS


def search_text(fields: PropertyFields) -> str:
    return normalize(f"{fields.address} {fields.zone}")[:300]


def _to_domain(model: PropertyModel) -> Property:
    return Property(
        id=model.id,
        tenant_id=model.tenant_id,
        fields=PropertyFields(
            title=model.title,
            address=model.address,
            operation=Operation(model.operation),
            zone=model.zone,
            price=model.price,
            currency=Currency(model.currency),
            rooms=model.rooms,
            link=model.link,
            status=PropertyStatus(model.status),
        ),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _copy(item: Property, model: PropertyModel) -> None:
    fields = item.fields
    model.title = fields.title
    model.address = fields.address
    model.operation = fields.operation.value
    model.zone = fields.zone
    model.price = fields.price
    model.currency = fields.currency.value
    model.rooms = fields.rooms
    model.link = fields.link
    model.status = fields.status.value
    model.search_text = search_text(fields)
    model.updated_at = item.updated_at


def _inquiries():
    """Distinct real leads (simulator tests excluded) the agent showed each property to."""
    return (
        select(func.count(func.distinct(LeadPropertyMatchModel.lead_id)))
        .join(LeadModel, LeadModel.id == LeadPropertyMatchModel.lead_id)
        .where(LeadPropertyMatchModel.property_id == PropertyModel.id, ~LeadModel.is_test)
        .scalar_subquery()
    )


class SqlAlchemyPropertyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, tenant_id: UUID, property_id: UUID) -> Property | None:
        model = self._session.get(PropertyModel, property_id)
        return _to_domain(model) if model is not None and model.tenant_id == tenant_id else None

    def get_by_link(self, tenant_id: UUID, link: str) -> Property | None:
        model = self._session.scalar(
            select(PropertyModel).where(
                PropertyModel.tenant_id == tenant_id, PropertyModel.link == link
            )
        )
        return _to_domain(model) if model is not None else None

    def add(self, item: Property) -> None:
        model = PropertyModel(id=item.id, tenant_id=item.tenant_id, created_at=item.created_at)
        _copy(item, model)
        self._session.add(model)
        self._session.flush()

    def update(self, item: Property) -> None:
        model = self._session.get(PropertyModel, item.id)
        if model is None or model.tenant_id != item.tenant_id:
            return
        _copy(item, model)
        self._session.flush()

    def list(
        self, tenant_id: UUID, filters: PropertyFilters, page: int, page_size: int
    ) -> PropertyPage:
        conditions = [PropertyModel.tenant_id == tenant_id]
        if filters.search and (term := normalize(filters.search)):
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append(PropertyModel.search_text.like(f"%{escaped}%", escape="\\"))
        if filters.operation is not None:
            conditions.append(PropertyModel.operation == filters.operation.value)
        if filters.status is not None:
            conditions.append(PropertyModel.status == filters.status.value)

        total = (
            self._session.scalar(select(func.count()).select_from(PropertyModel).where(*conditions))
            or 0
        )
        rows = self._session.execute(
            select(PropertyModel, _inquiries())
            .where(*conditions)
            .order_by(PropertyModel.created_at.desc(), PropertyModel.title, PropertyModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return PropertyPage(
            items=[PropertyRow(_to_domain(model), int(count or 0)) for model, count in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def published(self, tenant_id: UUID) -> Sequence[Property]:
        models = self._session.scalars(
            select(PropertyModel).where(
                PropertyModel.tenant_id == tenant_id,
                PropertyModel.status == PropertyStatus.PUBLISHED.value,
            )
        )
        return [_to_domain(model) for model in models]

    def has_any(self, tenant_id: UUID) -> bool:
        return bool(
            self._session.scalar(select(exists().where(PropertyModel.tenant_id == tenant_id)))
        )

    def has_published(self, tenant_id: UUID) -> bool:
        return bool(
            self._session.scalar(
                select(
                    exists().where(
                        PropertyModel.tenant_id == tenant_id,
                        PropertyModel.status == PropertyStatus.PUBLISHED.value,
                    )
                )
            )
        )


class SqlAlchemyPropertyImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: PropertyImport) -> None:
        self._session.add(
            PropertyImportModel(
                id=record.id,
                tenant_id=record.tenant_id,
                created_by_profile_id=record.created_by_profile_id,
                file_name=record.file_name,
                total=record.total,
                created=record.created,
                updated=record.updated,
                columns=list(record.columns),
                failed_rows=[
                    {"row": item.row, "error": item.error, "values": dict(item.values)}
                    for item in record.failed_rows
                ],
                created_at=record.created_at,
            )
        )
        self._session.flush()

    def get(self, tenant_id: UUID, import_id: UUID) -> PropertyImport | None:
        model = self._session.get(PropertyImportModel, import_id)
        if model is None or model.tenant_id != tenant_id:
            return None
        return PropertyImport(
            id=model.id,
            tenant_id=model.tenant_id,
            created_by_profile_id=model.created_by_profile_id,
            file_name=model.file_name,
            total=model.total,
            created=model.created,
            updated=model.updated,
            columns=list(model.columns),
            failed_rows=[
                FailedRow(item["row"], item["error"], item["values"]) for item in model.failed_rows
            ],
            created_at=model.created_at,
        )


class TenantPropertySearch:
    """The tenant's published properties; the sample fixture while it has none.

    As soon as one own property is published, the fixture is never used for that tenant.
    """

    def __init__(
        self,
        properties: SqlAlchemyPropertyRepository,
        samples: Sequence[Listing] = SAMPLE_LISTINGS,
    ) -> None:
        self._properties = properties
        self._samples = samples

    def search(self, tenant_id: UUID, query: PropertyQuery) -> Sequence[PropertyMatch]:
        own = self._properties.published(tenant_id)
        listings = [Listing.of(item) for item in own] if own else self._samples
        return rank(listings, query)

    def uses_samples(self, tenant_id: UUID) -> bool:
        return not self._properties.has_published(tenant_id)
