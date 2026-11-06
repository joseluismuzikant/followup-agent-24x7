"""Importing invoices: the sample files, the Spanish row errors, re-imports and formats."""

import csv
import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from conftest import SAMPLES, Owner
from cuentas_claras_api.container import get_clock
from cuentas_claras_api.invoices.application.rows import RowError, parse_amount, parse_date
from cuentas_claras_api.main import app
from sqlalchemy import text

# The samples' reference date, noon in Buenos Aires.
NOW = datetime(2026, 11, 2, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def pinned_clock(client):
    app.dependency_overrides[get_clock] = lambda: lambda: NOW


def _csv(*rows: list[str], header: str = "") -> bytes:
    lines = [header or ";".join(_HEADER), *(";".join(row) for row in rows)]
    return "\n".join(lines).encode("utf-8")


_HEADER = (SAMPLES / "facturas.csv").read_text(encoding="utf-8").splitlines()[0].split(";")


def _row(**values: str) -> list[str]:
    base = {
        "cliente": "Consorcio Test",
        "tipo": "B",
        "punto_venta": "3",
        "numero": "9001",
        "fecha_emision": "01/10/2026",
        "vencimiento": "10/10/2026",
        "monto": "1.000,00",
    }
    base.update(values)
    return [base.get(column, "") for column in _HEADER]


def test_the_sample_csv_imports_every_invoice(owner: Owner, sessions) -> None:
    report = owner.import_sample().json()

    assert (report["total"], report["created"], report["updated"], report["failed"]) == (
        40,
        40,
        0,
        0,
    )
    assert report["errors"] == [] and report["warnings"] == []
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM cc_clients")) == 25
        assert session.scalar(text("SELECT count(*) FROM cc_invoices WHERE status = 'paid'")) == 8


def test_the_sample_xlsx_gives_the_same_result(owner: Owner, sessions) -> None:
    report = owner.import_sample("facturas.xlsx").json()

    assert (report["total"], report["created"], report["failed"]) == (40, 40, 0)
    with sessions() as session:
        total = session.scalar(text("SELECT sum(amount) FROM cc_invoices"))
    csv_owner = Owner(owner.client, "Otra empresa")
    csv_owner.import_sample()
    with sessions() as session:
        both = session.scalar(text("SELECT sum(amount) FROM cc_invoices"))
    assert both == total * 2


def test_the_error_file_reports_each_row_in_spanish(owner: Owner) -> None:
    report = owner.import_sample("facturas-con-errores.csv").json()

    assert [error["error"] for error in report["errors"]] == [
        "Fila 7: el CUIT no es válido.",
        "Fila 12: falta el vencimiento.",
        "Fila 20: la fecha tiene que ser dd/mm/aaaa.",
        "Fila 31: el monto no es un número.",
    ]
    assert report["warnings"] == ["Fila 9: la factura ya figuraba pagada; no la cambiamos."]
    assert (report["total"], report["failed"]) == (31, 4)
    assert report["created"] + report["updated"] + report["skipped"] == 27

    download = owner.get(f"/invoices/import/{report['id']}/errors.csv")
    lines = list(csv.reader(io.StringIO(download.content.decode("utf-8-sig")), delimiter=";"))
    assert lines[0][:2] == ["error", "cliente"]
    assert [line[0] for line in lines[1:]] == [error["error"] for error in report["errors"]]
    assert download.headers["content-type"].startswith("text/csv")


def test_reimporting_updates_open_invoices_and_never_reopens_paid_ones(
    owner: Owner, sessions
) -> None:
    owner.import_sample()
    changed = _csv(
        _row(
            cliente="Consorcio Güemes 2140",
            numero="1203",
            monto="200.000,00",
            vencimiento="30/11/2026",
        ),
        _row(cliente="Consorcio Güemes 2140", numero="1201", vencimiento="01/10/2026"),
    )

    report = owner.upload("/invoices/import", "otra.csv", changed).json()

    assert (report["updated"], report["skipped"], report["created"]) == (1, 1, 0)
    assert report["warnings"] == ["Fila 3: la factura ya figuraba pagada; no la cambiamos."]
    with sessions() as session:
        amount, status = session.execute(
            text("SELECT amount, status FROM cc_invoices WHERE number = 1203")
        ).one()
        paid = session.scalar(text("SELECT status FROM cc_invoices WHERE number = 1201"))
        clients = session.scalar(text("SELECT count(*) FROM cc_clients"))
    assert (amount, status, paid, clients) == (Decimal("200000.00"), "open", "paid", 25)


def test_clients_are_matched_by_cuit_then_by_name(owner: Owner, sessions) -> None:
    rows = _csv(
        _row(cliente="Edificio  GÜEMES S.A.", numero="1", cuit=""),
        _row(cliente="edificio guemes sa", numero="2", whatsapp="11 5555-0199"),
        _row(cliente="Nombre cambiado", numero="3", cuit="30-71234567-1"),
        _row(cliente="Otro nombre", numero="4", cuit="30712345671"),
    )

    report = owner.upload("/invoices/import", "clientes.csv", rows).json()

    assert report["created"] == 4
    with sessions() as session:
        clients = session.execute(
            text("SELECT name, cuit, whatsapp FROM cc_clients ORDER BY created_at")
        ).all()
    assert len(clients) == 2
    # A later row fills in what the first one left empty.
    assert clients[0].whatsapp == "+5491155550199"
    assert clients[1].cuit == "30712345671"


def test_latin1_semicolons_and_commas(owner: Owner) -> None:
    latin1 = (
        ";".join(_HEADER).encode("cp1252")
        + b"\n"
        + ";".join(_row(cliente="Peña Hermanos", numero="10")).encode("cp1252")
    )
    comma = (",".join(_HEADER) + "\n" + ",".join(_row(numero="11", monto="1500"))).encode()

    assert owner.upload("/invoices/import", "latin1.csv", latin1).json()["created"] == 1
    assert owner.upload("/invoices/import", "comma.csv", comma).json()["created"] == 1
    clients = owner.get("/clients?q=pena").json()["items"]
    assert [client["name"] for client in clients] == ["Peña Hermanos"]


@pytest.mark.parametrize(
    ("text_", "expected"),
    [
        ("180.000,50", Decimal("180000.50")),
        ("$ 180.000", Decimal("180000")),
        ("180000", Decimal("180000")),
        ("180000.5", Decimal("180000.50")),
        ("1.500", Decimal("1500")),
    ],
)
def test_argentine_amounts(text_: str, expected: Decimal) -> None:
    assert parse_amount(text_) == expected


def test_dates_are_day_first() -> None:
    assert parse_date("05/11/2026") == date(2026, 11, 5)
    assert parse_date("2026-11-05") == date(2026, 11, 5)  # an XLSX date cell
    for wrong in ("11/31/2026", "2026/11/05", "5-11-2026"):
        with pytest.raises(RowError):
            parse_date(wrong)


def test_limits_and_unreadable_files(owner: Owner) -> None:
    assert (
        owner.upload("/invoices/import", "big.csv", b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    )
    too_many = _csv(*(_row(numero=str(n)) for n in range(1, 5002)))
    assert owner.upload("/invoices/import", "many.csv", too_many).status_code == 413
    assert owner.upload("/invoices/import", "x.csv", b"").json()["code"] == "import_file_invalid"
    assert (
        owner.upload("/invoices/import", "x.csv", b"a;b\n1;2").json()["code"]
        == "import_file_invalid"
    )


def test_the_template_has_every_column(owner: Owner) -> None:
    response = owner.get("/invoices/import-template.csv")

    header = response.content.decode("utf-8-sig").splitlines()[0].split(";")
    assert header == _HEADER
