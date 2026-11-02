"""S7 Propiedades: list, manual create/edit, publish/pause and spreadsheet import."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from followup_core.identity.domain.profile import Profile, Role
from pydantic import BaseModel

from ..auth import current_profile, require_role
from ..http_errors import ApiError
from .application.properties import (
    CreateProperty,
    GetImportErrors,
    ImportProperties,
    ListProperties,
    SetPropertyStatus,
    UpdateProperty,
    import_template,
)
from .domain.errors import (
    ImportFileInvalidError,
    ImportNotFoundError,
    ImportTooLargeError,
    PropertyInvalidError,
    PropertyLinkTakenError,
    PropertyNotFoundError,
)
from .domain.imports import MAX_IMPORT_BYTES, PropertyImport
from .domain.property import (
    Currency,
    Operation,
    Property,
    PropertyChanges,
    PropertyFields,
    PropertyStatus,
    default_currency,
)
from .domain.repositories import PropertyFilters

OperationName = Literal["sale", "rent"]
CurrencyName = Literal["ARS", "USD"]
StatusName = Literal["published", "paused"]

WriterDep = Annotated[Profile, Depends(require_role(Role.OWNER, Role.MANAGER))]
ReaderDep = Annotated[Profile, Depends(current_profile)]


class PropertyRead(BaseModel):
    id: UUID
    title: str
    address: str
    operation: OperationName
    zone: str
    price: int
    currency: CurrencyName
    rooms: int
    link: str
    status: StatusName
    inquiries: int
    created_at: datetime
    updated_at: datetime


class PropertyListRead(BaseModel):
    items: list[PropertyRead]
    total: int
    page: int
    page_size: int


class PropertyCreate(BaseModel):
    title: str
    address: str
    operation: OperationName
    zone: str
    price: int
    # Defaults to USD for sales and ARS for rents.
    currency: CurrencyName | None = None
    rooms: int
    link: str
    status: StatusName = "published"


class PropertyUpdate(BaseModel):
    title: str | None = None
    address: str | None = None
    operation: OperationName | None = None
    zone: str | None = None
    price: int | None = None
    currency: CurrencyName | None = None
    rooms: int | None = None
    link: str | None = None
    status: StatusName | None = None


class ImportReportRead(BaseModel):
    id: UUID
    file_name: str
    total: int
    imported: int
    created: int
    updated: int
    failed: int
    # Row errors in Spanish, as shown in S7: "Fila 12: falta el precio."
    errors: list[str]


def property_read(item: Property, inquiries: int = 0) -> PropertyRead:
    fields = item.fields
    return PropertyRead(
        id=item.id,
        title=fields.title,
        address=fields.address,
        operation=fields.operation.value,
        zone=fields.zone,
        price=fields.price,
        currency=fields.currency.value,
        rooms=fields.rooms,
        link=fields.link,
        status=fields.status.value,
        inquiries=inquiries,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def import_report(record: PropertyImport) -> ImportReportRead:
    return ImportReportRead(
        id=record.id,
        file_name=record.file_name,
        total=record.total,
        imported=record.imported,
        created=record.created,
        updated=record.updated,
        failed=record.failed,
        errors=[item.error for item in record.failed_rows],
    )


def _csv_response(content: str, file_name: str) -> Response:
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


def _not_found() -> ApiError:
    return ApiError(404, "property_not_found")


def build_properties_router(
    list_factory: Callable[..., ListProperties],
    create_factory: Callable[..., CreateProperty],
    update_factory: Callable[..., UpdateProperty],
    status_factory: Callable[..., SetPropertyStatus],
    import_factory: Callable[..., ImportProperties],
    import_errors_factory: Callable[..., GetImportErrors],
) -> APIRouter:
    router = APIRouter(tags=["properties"])

    @router.get("/properties", response_model=PropertyListRead)
    def list_properties(
        profile: ReaderDep,
        use_case: Annotated[ListProperties, Depends(list_factory)],
        search: Annotated[str | None, Query(max_length=100)] = None,
        operation: OperationName | None = None,
        status: StatusName | None = None,
        page: Annotated[int, Query(ge=1)] = 1,
    ) -> PropertyListRead:
        result = use_case.execute(
            profile.tenant_id,
            PropertyFilters(
                search=search,
                operation=Operation(operation) if operation else None,
                status=PropertyStatus(status) if status else None,
            ),
            page,
        )
        return PropertyListRead(
            items=[property_read(row.property, row.inquiries) for row in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    @router.post("/properties", response_model=PropertyRead, status_code=201)
    def create_property(
        payload: PropertyCreate,
        profile: WriterDep,
        use_case: Annotated[CreateProperty, Depends(create_factory)],
    ) -> PropertyRead:
        operation = Operation(payload.operation)
        fields = PropertyFields(
            title=payload.title,
            address=payload.address,
            operation=operation,
            zone=payload.zone,
            price=payload.price,
            currency=Currency(payload.currency)
            if payload.currency
            else default_currency(operation),
            rooms=payload.rooms,
            link=payload.link,
            status=PropertyStatus(payload.status),
        )
        try:
            return property_read(use_case.execute(profile.tenant_id, fields))
        except PropertyInvalidError as error:
            raise ApiError(422, "property_invalid") from error
        except PropertyLinkTakenError as error:
            raise ApiError(409, "property_link_taken") from error

    @router.patch("/properties/{property_id}", response_model=PropertyRead)
    def update_property(
        property_id: UUID,
        payload: PropertyUpdate,
        profile: WriterDep,
        use_case: Annotated[UpdateProperty, Depends(update_factory)],
    ) -> PropertyRead:
        changes = PropertyChanges(
            title=payload.title,
            address=payload.address,
            operation=Operation(payload.operation) if payload.operation else None,
            zone=payload.zone,
            price=payload.price,
            currency=Currency(payload.currency) if payload.currency else None,
            rooms=payload.rooms,
            link=payload.link,
            status=PropertyStatus(payload.status) if payload.status else None,
        )
        try:
            return property_read(use_case.execute(profile.tenant_id, property_id, changes))
        except PropertyNotFoundError as error:
            raise _not_found() from error
        except PropertyInvalidError as error:
            raise ApiError(422, "property_invalid") from error
        except PropertyLinkTakenError as error:
            raise ApiError(409, "property_link_taken") from error

    def _set_status(
        profile: Profile, property_id: UUID, use_case: SetPropertyStatus, status: PropertyStatus
    ) -> PropertyRead:
        try:
            return property_read(use_case.execute(profile.tenant_id, property_id, status))
        except PropertyNotFoundError as error:
            raise _not_found() from error

    @router.post("/properties/{property_id}/publish", response_model=PropertyRead)
    def publish_property(
        property_id: UUID,
        profile: WriterDep,
        use_case: Annotated[SetPropertyStatus, Depends(status_factory)],
    ) -> PropertyRead:
        return _set_status(profile, property_id, use_case, PropertyStatus.PUBLISHED)

    @router.post("/properties/{property_id}/pause", response_model=PropertyRead)
    def pause_property(
        property_id: UUID,
        profile: WriterDep,
        use_case: Annotated[SetPropertyStatus, Depends(status_factory)],
    ) -> PropertyRead:
        return _set_status(profile, property_id, use_case, PropertyStatus.PAUSED)

    @router.post("/properties/import", response_model=ImportReportRead)
    def import_properties(
        file: Annotated[UploadFile, File()],
        profile: WriterDep,
        use_case: Annotated[ImportProperties, Depends(import_factory)],
    ) -> ImportReportRead:
        # One byte over the limit is enough to reject the file without reading all of it.
        content = file.file.read(MAX_IMPORT_BYTES + 1)
        try:
            record = use_case.execute(
                profile.tenant_id, profile.id, file.filename or "propiedades", content
            )
        except ImportTooLargeError as error:
            raise ApiError(413, "import_too_large") from error
        except ImportFileInvalidError as error:
            raise ApiError(422, "import_file_invalid") from error
        return import_report(record)

    @router.get(
        "/properties/import/{import_id}/errors.csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def download_import_errors(
        import_id: UUID,
        profile: ReaderDep,
        use_case: Annotated[GetImportErrors, Depends(import_errors_factory)],
    ) -> Response:
        try:
            content = use_case.execute(profile.tenant_id, import_id)
        except ImportNotFoundError as error:
            raise ApiError(404, "import_not_found") from error
        return _csv_response(content, "propiedades-con-errores.csv")

    @router.get(
        "/properties/import-template.csv",
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}},
    )
    def download_import_template(_profile: ReaderDep) -> Response:
        return _csv_response(import_template(), "plantilla-propiedades.csv")

    return router
