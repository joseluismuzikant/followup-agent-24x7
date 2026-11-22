"""S7 Propiedades: list, manual create/edit, publish/pause and spreadsheet import."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from followup_core.identity.domain.profile import Profile, Role
from pydantic import BaseModel, Field

from ..auth import current_profile, require_role
from ..http_errors import ApiError
from .application.listing import ListingResult, ReadListing, RefreshResult
from .application.properties import (
    CreateProperty,
    GetImportErrors,
    ImportProperties,
    ListProperties,
    SetPropertyStatus,
    UpdateProperty,
    import_template,
)
from .domain.conditions import (
    MAX_CONDITIONS_TEXT,
    MAX_CONTRACT_MONTHS,
    ConditionSettings,
    ConditionsInvalidError,
    Guarantee,
    PropertyConditions,
)
from .domain.errors import (
    ImportFileInvalidError,
    ImportNotFoundError,
    ImportTooLargeError,
    PropertyInvalidError,
    PropertyLinkTakenError,
    PropertyManagedExternallyError,
    PropertyNotFoundError,
)
from .domain.imports import MAX_IMPORT_BYTES, PropertyImport
from .domain.listing import (
    LinkReadLimitError,
    ListingDraft,
    ListingTextError,
    ListingUrlError,
    portal_name,
    problem_message,
)
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


class ConditionSettingsStore(Protocol):
    def get(self, tenant_id: UUID) -> ConditionSettings: ...


SaveSettings = Callable[[UUID, UUID, ConditionSettings], ConditionSettings]

OperationName = Literal["sale", "rent"]
CurrencyName = Literal["ARS", "USD"]
StatusName = Literal["published", "paused"]

GuaranteeName = Literal["propietaria", "caucion", "recibo_de_sueldo", "otra"]

WriterDep = Annotated[Profile, Depends(require_role(Role.OWNER, Role.MANAGER))]
ReaderDep = Annotated[Profile, Depends(current_profile)]


class ConditionsModel(BaseModel):
    """Requirements and features; null = no informado. Only those of the operation apply."""

    garantias: list[GuaranteeName] | None = None
    contrato_minimo_meses: int | None = Field(default=None, ge=1, le=MAX_CONTRACT_MONTHS)
    temporal: bool | None = None
    amueblado: bool | None = None
    mascotas: bool | None = None
    apto_profesional: bool | None = None
    apto_credito: bool | None = None
    acepta_financiacion: bool | None = None
    acepta_permuta: bool | None = None
    condiciones: str | None = Field(default=None, max_length=MAX_CONDITIONS_TEXT)


def conditions_model(conditions: PropertyConditions) -> ConditionsModel:
    return ConditionsModel(**conditions.to_json())


def conditions_from(model: ConditionsModel | None) -> PropertyConditions:
    if model is None:
        return PropertyConditions()
    try:
        return PropertyConditions(
            garantias=frozenset(Guarantee(item) for item in model.garantias)
            if model.garantias
            else None,
            contrato_minimo_meses=model.contrato_minimo_meses,
            temporal=model.temporal,
            amueblado=model.amueblado,
            mascotas=model.mascotas,
            apto_profesional=model.apto_profesional,
            apto_credito=model.apto_credito,
            acepta_financiacion=model.acepta_financiacion,
            acepta_permuta=model.acepta_permuta,
            condiciones=model.condiciones,
        )
    except ConditionsInvalidError as error:
        raise ApiError(422, "conditions_invalid", field=error.field) from error


class ConditionSettingsRead(BaseModel):
    """ "Condiciones generales": defaults per operation and Sofía's behavior."""

    rent: ConditionsModel
    sale: ConditionsModel
    warn_before_visit: bool
    offer_alternatives: bool
    notify_mismatches: bool


class ConditionSettingsWrite(ConditionSettingsRead):
    pass


def settings_read(settings: ConditionSettings) -> ConditionSettingsRead:
    return ConditionSettingsRead(
        rent=conditions_model(settings.defaults(Operation.RENT)),
        sale=conditions_model(settings.defaults(Operation.SALE)),
        warn_before_visit=settings.warn_before_visit,
        offer_alternatives=settings.offer_alternatives,
        notify_mismatches=settings.notify_mismatches,
    )


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
    # The property's own conditions, what applies (own over the agency's defaults) and which
    # fields come from the defaults.
    conditions: ConditionsModel
    effective_conditions: ConditionsModel
    from_defaults: list[str]
    # manual (the form or a spreadsheet) or tokko: a Tokko listing is edited in Tokko, only
    # its conditions here.
    source: Literal["manual", "tokko"] = "manual"
    external_id: str | None = None
    external_ref: str | None = None


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
    conditions: ConditionsModel | None = None


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
    # Replaces the property's conditions when sent.
    conditions: ConditionsModel | None = None


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
    # Cells ignored: "Fila 4: «apto_credito» no aplica a un alquiler; lo ignoramos."
    warnings: list[str]


class ListingLinkRequest(BaseModel):
    url: str = Field(max_length=2000)


class ListingTextRequest(BaseModel):
    # The publication's text as copied (Ctrl+A, Ctrl+C); only the first 15,000 characters
    # without the page's menus are read.
    text: str = Field(max_length=200_000)
    link: str = Field(max_length=2000)


class ListingRefreshRequest(BaseModel):
    # The publication's text, when its portal does not let us read the link.
    text: str | None = Field(default=None, max_length=200_000)


class ListingDraftRead(BaseModel):
    """A property read from its publication, not saved. Empty / null = not found."""

    link: str
    title: str
    address: str
    operation: OperationName | None
    zone: str
    price: int | None
    currency: CurrencyName | None
    rooms: int | None
    status: StatusName | None
    conditions: ConditionsModel
    # For the preview only (photos are not stored yet).
    image_url: str | None
    floor_area_m2: int | None
    # Where each field came from: "structured" (the page's data) or "model" (read by the
    # model: "Revisá este dato").
    sources: dict[str, Literal["structured", "model"]]
    # Why the page could not be read (blocked, gone, unreachable, timeout, too_large,
    # not_html, not_listing), in Spanish in `message`; the form opens with the link anyway.
    problem: str | None
    message: str | None
    # The portal's name from the link ("Zonaprop"), for the messages.
    portal: str
    warnings: list[str]
    # The agency already has a property with this link.
    duplicate: PropertyRead | None = None


class FieldChangeRead(BaseModel):
    field: str
    current: str | int | None
    read: str | int | None


class ListingRefreshRead(BaseModel):
    draft: ListingDraftRead
    # What the publication says differently, to apply field by field.
    changes: list[FieldChangeRead]


def _plain(value: object) -> str | int | None:
    if value is None or isinstance(value, int):
        return value
    return str(value)


def draft_read(draft: ListingDraft, duplicate: PropertyRead | None = None) -> ListingDraftRead:
    return ListingDraftRead(
        link=draft.link,
        title=draft.title,
        address=draft.address,
        operation=draft.operation.value if draft.operation else None,
        zone=draft.zone,
        price=draft.price,
        currency=draft.currency.value if draft.currency else None,
        rooms=draft.rooms,
        status=draft.status.value if draft.status else None,
        conditions=conditions_model(draft.conditions),
        image_url=draft.image_url,
        floor_area_m2=draft.floor_area_m2,
        sources={name: source.value for name, source in draft.sources.items()},  # type: ignore[misc]
        problem=draft.problem.value if draft.problem else None,
        message=problem_message(draft.problem, draft.link) if draft.problem else None,
        portal=portal_name(draft.link),
        warnings=list(draft.warnings),
        duplicate=duplicate,
    )


def property_read(
    item: Property, inquiries: int = 0, settings: ConditionSettings | None = None
) -> PropertyRead:
    fields = item.fields
    settings = settings or ConditionSettings()
    defaults = settings.defaults(fields.operation)
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
        conditions=conditions_model(fields.conditions),
        effective_conditions=conditions_model(fields.conditions.over(defaults)),
        from_defaults=sorted(fields.conditions.from_defaults(defaults)),
        source=item.source.value,  # type: ignore[arg-type]
        external_id=item.external_id,
        external_ref=item.external_ref,
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
        warnings=list(record.warnings),
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
    settings_factory: Callable[..., ConditionSettingsStore],
    save_settings_factory: Callable[..., SaveSettings],
    read_listing_factory: Callable[..., ReadListing],
) -> APIRouter:
    router = APIRouter(tags=["properties"])

    def listing_read(result: ListingResult, settings: ConditionSettingsStore, tenant_id: UUID):
        duplicate = (
            property_read(result.duplicate, 0, settings.get(tenant_id))
            if result.duplicate
            else None
        )
        return draft_read(result.draft, duplicate)

    @router.post("/properties/from-link", response_model=ListingDraftRead)
    def read_from_link(
        payload: ListingLinkRequest,
        profile: WriterDep,
        use_case: Annotated[ReadListing, Depends(read_listing_factory)],
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
    ) -> ListingDraftRead:
        """ "Cargar desde un link": a draft for the form. Nothing is saved."""
        try:
            result = use_case.from_link(profile.tenant_id, profile.id, payload.url)
        except ListingUrlError as error:
            raise ApiError(422, "listing_url_invalid") from error
        except LinkReadLimitError as error:
            raise ApiError(429, "listing_read_limit") from error
        return listing_read(result, settings, profile.tenant_id)

    @router.post("/properties/from-text", response_model=ListingDraftRead)
    def read_from_text(
        payload: ListingTextRequest,
        profile: WriterDep,
        use_case: Annotated[ReadListing, Depends(read_listing_factory)],
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
    ) -> ListingDraftRead:
        """ "Pegar texto de la publicación", for portals that block reading the link."""
        try:
            result = use_case.from_text(profile.tenant_id, profile.id, payload.text, payload.link)
        except ListingUrlError as error:
            raise ApiError(422, "listing_url_invalid") from error
        except ListingTextError as error:
            raise ApiError(422, "listing_text_too_short") from error
        except LinkReadLimitError as error:
            raise ApiError(429, "listing_read_limit") from error
        return listing_read(result, settings, profile.tenant_id)

    @router.post("/properties/{property_id}/refresh-from-link", response_model=ListingRefreshRead)
    def refresh_from_link(
        property_id: UUID,
        payload: ListingRefreshRequest,
        profile: WriterDep,
        use_case: Annotated[ReadListing, Depends(read_listing_factory)],
    ) -> ListingRefreshRead:
        """ "Actualizar desde el link": what the publication says now, as changes to apply."""
        try:
            result: RefreshResult = use_case.refresh(
                profile.tenant_id, profile.id, property_id, payload.text
            )
        except PropertyNotFoundError as error:
            raise _not_found() from error
        except PropertyManagedExternallyError as error:
            raise ApiError(409, "property_managed_by_tokko") from error
        except ListingTextError as error:
            raise ApiError(422, "listing_text_too_short") from error
        except LinkReadLimitError as error:
            raise ApiError(429, "listing_read_limit") from error
        except ListingUrlError as error:
            raise ApiError(422, "listing_url_invalid") from error
        return ListingRefreshRead(
            draft=draft_read(result.draft),
            changes=[
                FieldChangeRead(
                    field=change.field, current=_plain(change.current), read=_plain(change.read)
                )
                for change in result.changes
            ],
        )

    @router.get("/properties", response_model=PropertyListRead)
    def list_properties(
        profile: ReaderDep,
        use_case: Annotated[ListProperties, Depends(list_factory)],
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
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
        agency = settings.get(profile.tenant_id)
        return PropertyListRead(
            items=[property_read(row.property, row.inquiries, agency) for row in result.items],
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    @router.post("/properties", response_model=PropertyRead, status_code=201)
    def create_property(
        payload: PropertyCreate,
        profile: WriterDep,
        use_case: Annotated[CreateProperty, Depends(create_factory)],
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
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
            conditions=conditions_from(payload.conditions),
        )
        try:
            return property_read(
                use_case.execute(profile.tenant_id, fields), 0, settings.get(profile.tenant_id)
            )
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
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
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
            conditions=conditions_from(payload.conditions) if payload.conditions else None,
        )
        try:
            return property_read(
                use_case.execute(profile.tenant_id, property_id, changes),
                0,
                settings.get(profile.tenant_id),
            )
        except PropertyNotFoundError as error:
            raise _not_found() from error
        except PropertyManagedExternallyError as error:
            raise ApiError(409, "property_managed_by_tokko") from error
        except PropertyInvalidError as error:
            raise ApiError(422, "property_invalid") from error
        except PropertyLinkTakenError as error:
            raise ApiError(409, "property_link_taken") from error

    def _set_status(
        profile: Profile,
        property_id: UUID,
        use_case: SetPropertyStatus,
        status: PropertyStatus,
        settings: ConditionSettingsStore,
    ) -> PropertyRead:
        try:
            return property_read(
                use_case.execute(profile.tenant_id, property_id, status),
                0,
                settings.get(profile.tenant_id),
            )
        except PropertyNotFoundError as error:
            raise _not_found() from error
        except PropertyManagedExternallyError as error:
            raise ApiError(409, "property_managed_by_tokko") from error

    @router.post("/properties/{property_id}/publish", response_model=PropertyRead)
    def publish_property(
        property_id: UUID,
        profile: WriterDep,
        use_case: Annotated[SetPropertyStatus, Depends(status_factory)],
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
    ) -> PropertyRead:
        return _set_status(profile, property_id, use_case, PropertyStatus.PUBLISHED, settings)

    @router.post("/properties/{property_id}/pause", response_model=PropertyRead)
    def pause_property(
        property_id: UUID,
        profile: WriterDep,
        use_case: Annotated[SetPropertyStatus, Depends(status_factory)],
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
    ) -> PropertyRead:
        return _set_status(profile, property_id, use_case, PropertyStatus.PAUSED, settings)

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

    @router.get("/condition-settings", response_model=ConditionSettingsRead)
    def get_condition_settings(
        profile: ReaderDep,
        settings: Annotated[ConditionSettingsStore, Depends(settings_factory)],
    ) -> ConditionSettingsRead:
        return settings_read(settings.get(profile.tenant_id))

    @router.put("/condition-settings", response_model=ConditionSettingsRead)
    def save_condition_settings(
        payload: ConditionSettingsWrite,
        profile: WriterDep,
        save: Annotated[SaveSettings, Depends(save_settings_factory)],
    ) -> ConditionSettingsRead:
        """ "Condiciones generales" (Configuración)."""
        saved = save(
            profile.tenant_id,
            profile.id,
            ConditionSettings(
                rent=conditions_from(payload.rent),
                sale=conditions_from(payload.sale),
                warn_before_visit=payload.warn_before_visit,
                offer_alternatives=payload.offer_alternatives,
                notify_mismatches=payload.notify_mismatches,
            ),
        )
        return settings_read(saved)

    return router
