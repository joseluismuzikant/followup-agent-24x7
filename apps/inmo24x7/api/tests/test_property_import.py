"""Spreadsheet import without the database: reading files, Argentine numbers and the S7 row
errors."""

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from inmo24x7_api.properties.application.properties import (
    GetImportErrors,
    ImportProperties,
    import_template,
)
from inmo24x7_api.properties.application.rows import ColumnMap, parse_amount, parse_price
from inmo24x7_api.properties.domain.errors import ImportFileInvalidError, ImportTooLargeError
from inmo24x7_api.properties.domain.imports import MAX_IMPORT_BYTES, PropertyImport
from inmo24x7_api.properties.domain.property import (
    Currency,
    Operation,
    Property,
    PropertyStatus,
)
from inmo24x7_api.properties.domain.repositories import PropertyFilters, PropertyPage
from inmo24x7_api.properties.infrastructure.spreadsheet import read_spreadsheet

SAMPLES = Path(__file__).resolve().parents[4] / "docs" / "samples"
HEADER = "titulo,direccion,operacion,zona,precio,moneda,ambientes,link,estado"
NOW = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)


class InMemoryProperties:
    def __init__(self) -> None:
        self.items: dict[UUID, Property] = {}
        self.writes = 0

    def get(self, tenant_id: UUID, property_id: UUID) -> Property | None:
        item = self.items.get(property_id)
        return item if item and item.tenant_id == tenant_id else None

    def get_by_link(self, tenant_id: UUID, link: str) -> Property | None:
        return next(
            (p for p in self.items.values() if p.tenant_id == tenant_id and p.fields.link == link),
            None,
        )

    def add(self, item: Property) -> None:
        self.items[item.id] = item
        self.writes += 1

    def update(self, item: Property) -> None:
        self.items[item.id] = item
        self.writes += 1

    def list(
        self, tenant_id: UUID, filters: PropertyFilters, page: int, page_size: int
    ) -> PropertyPage:
        raise NotImplementedError

    def published(self, tenant_id: UUID) -> Sequence[Property]:
        return [p for p in self.items.values() if p.tenant_id == tenant_id and p.is_published]

    def has_any(self, tenant_id: UUID) -> bool:
        return any(p.tenant_id == tenant_id for p in self.items.values())

    def has_published(self, tenant_id: UUID) -> bool:
        return bool(self.published(tenant_id))


class InMemoryImports:
    def __init__(self) -> None:
        self.records: dict[UUID, PropertyImport] = {}

    def add(self, record: PropertyImport) -> None:
        self.records[record.id] = record

    def get(self, tenant_id: UUID, import_id: UUID) -> PropertyImport | None:
        record = self.records.get(import_id)
        return record if record and record.tenant_id == tenant_id else None


class Importer:
    def __init__(self) -> None:
        self.tenant_id = uuid4()
        self.properties = InMemoryProperties()
        self.imports = InMemoryImports()
        self.use_case = ImportProperties(
            self.properties, self.imports, read_spreadsheet, clock=lambda: NOW
        )

    def run(self, name: str, content: bytes) -> PropertyImport:
        return self.use_case.execute(self.tenant_id, None, name, content)

    def run_sample(self, name: str) -> PropertyImport:
        return self.run(name, (SAMPLES / name).read_bytes())


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("850.000", 850_000),
        ("850000", 850_000),
        ("1.250.000", 1_250_000),
        ("1.250.000,50", 1_250_000),
        ("185000.0", 185_000),
        ("185 000", 185_000),
        ("abc", None),
        ("12,345,678", None),
        ("", None),
    ],
)
def test_amounts_in_argentine_notation(text: str, amount: int | None) -> None:
    assert parse_amount(text) == amount


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("USD 185.000", (185_000, Currency.USD)),
        ("U$S 185.000", (185_000, Currency.USD)),
        ("$ 900.000", (900_000, Currency.ARS)),
        ("900.000 pesos", (900_000, Currency.ARS)),
        ("850.000", (850_000, None)),
    ],
)
def test_prices_carry_their_currency(text: str, expected: tuple) -> None:
    assert parse_price(text) == expected


def test_sample_csv_imports_every_row_with_the_right_values() -> None:
    importer = Importer()

    report = importer.run_sample("propiedades.csv")

    assert (report.total, report.imported, report.created, report.failed) == (20, 20, 20, 0)
    by_link = {
        p.fields.link.rsplit("/", 1)[-1]: p.fields for p in importer.properties.items.values()
    }
    guatemala = by_link["guatemala-5200"]
    # "$ 1.250.000" with an empty currency column on a rent.
    assert (guatemala.price, guatemala.currency, guatemala.operation) == (
        1_250_000,
        Currency.ARS,
        Operation.RENT,
    )
    # "USD 168.000" on a sale without a currency column value.
    assert (by_link["soler-5600"].price, by_link["soler-5600"].currency) == (168_000, Currency.USD)
    assert by_link["alvear-1600"].status is PropertyStatus.PAUSED
    assert by_link["arevalo-2100"].zone == "Colegiales"


def test_sample_xlsx_imports_the_same_rows() -> None:
    csv_import, xlsx_import = Importer(), Importer()
    csv_import.run_sample("propiedades.csv")

    report = xlsx_import.run_sample("propiedades.xlsx")

    assert (report.total, report.imported, report.failed) == (20, 20, 0)
    fields = lambda importer: sorted(  # noqa: E731
        (p.fields for p in importer.properties.items.values()), key=lambda f: f.link
    )
    assert fields(xlsx_import) == fields(csv_import)


def test_the_errors_file_reports_exactly_the_three_s7_messages() -> None:
    importer = Importer()

    report = importer.run_sample("propiedades-con-errores.csv")

    assert (report.total, report.imported, report.failed) == (5, 2, 3)
    assert [row.error for row in report.failed_rows] == [
        "Fila 3: falta el precio.",
        "Fila 5: el link no es una dirección web válida.",
        "Fila 6: la operación tiene que ser «venta» o «alquiler».",
    ]


def test_the_error_report_has_the_original_rows_plus_an_error_column() -> None:
    importer = Importer()
    report = importer.run_sample("propiedades-con-errores.csv")

    content = GetImportErrors(importer.imports).execute(importer.tenant_id, report.id)

    lines = content.lstrip("﻿").splitlines()
    assert lines[0] == f"{HEADER},error"
    assert len(lines) == 4
    assert lines[1].startswith("3 ambientes sin precio,Malabia 1800,alquiler,Palermo,,ARS,3,")
    assert lines[1].endswith(",Fila 3: falta el precio.")
    assert "ver en la web" in lines[2]


def test_latin1_and_semicolons_are_read() -> None:
    content = (
        "Título;Dirección;Operación;Zona;Precio;Moneda;Ambientes;Link;Estado\n"
        "Depto con balcón;Güemes 4300;alquiler;Palermo;850.000;;2;"
        "https://ejemplo.com.ar/guemes;publicada\n"
    ).encode("latin-1")
    importer = Importer()

    report = importer.run("propiedades.csv", content)

    assert report.created == 1
    (item,) = importer.properties.items.values()
    assert (item.fields.title, item.fields.address) == ("Depto con balcón", "Güemes 4300")


def test_reimporting_updates_by_link_and_unchanged_rows_are_not_written() -> None:
    importer = Importer()
    importer.run_sample("propiedades.csv")
    writes = importer.properties.writes

    again = importer.run_sample("propiedades.csv")
    assert (again.created, again.updated) == (0, 20)
    assert importer.properties.writes == writes

    changed = (
        f"{HEADER}\n2 ambientes luminoso,Gorriti 4800,alquiler,Palermo,870.000,ARS,2,"
        "https://www.inmobiliariasur.example/propiedades/gorriti-4800,pausada\n"
    ).encode()
    report = importer.run("cambios.csv", changed)

    assert (report.created, report.updated) == (0, 1)
    assert len(importer.properties.items) == 20
    gorriti = importer.properties.get_by_link(
        importer.tenant_id, "https://www.inmobiliariasur.example/propiedades/gorriti-4800"
    )
    assert gorriti is not None
    assert (gorriti.fields.price, gorriti.fields.status) == (870_000, PropertyStatus.PAUSED)


def test_files_over_5_mb_are_rejected() -> None:
    with pytest.raises(ImportTooLargeError):
        Importer().run("grande.csv", b"x" * (MAX_IMPORT_BYTES + 1))


def test_more_than_2000_rows_are_rejected() -> None:
    row = "Depto,Calle {n},venta,Palermo,USD 100.000,USD,2,https://ejemplo.com.ar/{n},publicada"
    content = "\n".join([HEADER, *(row.format(n=n) for n in range(2001))]).encode()

    with pytest.raises(ImportTooLargeError):
        Importer().run("muchas.csv", content)


@pytest.mark.parametrize(
    "content",
    [b"", b"nombre,precio\nCasa,100\n", b"PK\x03\x04 not really a workbook"],
)
def test_unreadable_files_or_missing_columns_are_invalid(content: bytes) -> None:
    with pytest.raises(ImportFileInvalidError):
        Importer().run("archivo.xlsx" if content.startswith(b"PK") else "a.csv", content)


def test_the_template_has_the_spanish_headers_and_an_example() -> None:
    lines = import_template().lstrip("﻿").splitlines()

    assert lines[0] == HEADER
    assert ColumnMap.of(lines[0].split(","))
    assert len(lines) == 2
