"""Writes the Cuentas Claras sample files (facturas.csv, facturas.xlsx and
facturas-con-errores.csv) from one list, so they never drift apart:

    uv run --all-packages python docs/samples/cuentas-claras/make_samples.py

The data is made up: an elevator-maintenance company and its clients (buildings and
property managers). Due dates are relative to REFERENCE (see README.md).
"""

# ruff: noqa: E501 - the sample data reads best as one row per line.
import csv
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
REFERENCE = date(2026, 11, 2)
COLUMNS = (
    "cliente", "detalle_cliente", "cuit", "contacto", "whatsapp", "email", "tipo",
    "punto_venta", "numero", "fecha_emision", "vencimiento", "monto", "moneda", "descripcion",
    "estado", "fecha_pago", "medio_pago",
)  # fmt: skip
WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit(prefix: str, body: int) -> str:
    """A valid CUIT (check digit included) for a made-up company."""
    while True:
        digits = f"{prefix}{body:08d}"
        remainder = sum(int(d) * w for d, w in zip(digits, WEIGHTS, strict=True)) % 11
        if remainder != 1:
            check = 0 if remainder == 0 else 11 - remainder
            return f"{digits[:2]}-{digits[2:]}-{check}"
        body += 1


# name, subtitle, has CUIT, contact, WhatsApp (None = "Sin WhatsApp"), email
CLIENTS = [
    (
        "Consorcio Güemes 2140",
        "Administración Pérez",
        True,
        "Marta Pérez",
        "11 5555-0101",
        "admin.perez@ejemplo.com",
    ),
    ("Edificio Libertador 5800", "Mantenimiento mensual", True, "Jorge Ríos", "11 5555-0102", None),
    (
        "Torre Palermo Chico",
        "Administración Sosa",
        True,
        "Laura Sosa",
        "11 5555-0103",
        "lsosa@ejemplo.com",
    ),
    (
        "Consorcio Cabildo 1550",
        "Administración Pérez",
        True,
        "Marta Pérez",
        "11 5555-0101",
        "admin.perez@ejemplo.com",
    ),
    ("Edificio Juramento 2200", "2 ascensores", False, "Carlos Díaz", "11 5555-0105", None),
    (
        "Clínica San Martín",
        "Montacargas y ascensor",
        True,
        "Ana Gómez",
        "11 5555-0106",
        "compras@clinicasm.ejemplo.com",
    ),
    (
        "Hotel Recoleta Plaza",
        "Mantenimiento 24 h",
        True,
        "Diego Paz",
        "11 5555-0107",
        "mantenimiento@recoletaplaza.ejemplo.com",
    ),
    (
        "Consorcio Rivadavia 7300",
        "Administración Lema",
        True,
        "Rosa Lema",
        None,
        "rlema@ejemplo.com",
    ),
    ("Edificio Belgrano R", "Mantenimiento mensual", False, "Pablo Ruiz", "11 5555-0109", None),
    (
        "Colegio Nuestra Señora",
        "Ascensor adaptado",
        True,
        "Hna. Teresa",
        "11 5555-0110",
        "administracion@colegions.ejemplo.com",
    ),
    (
        "Consorcio Santa Fe 3300",
        "Administración Lema",
        True,
        "Rosa Lema",
        None,
        "rlema@ejemplo.com",
    ),
    (
        "Oficinas Catalinas Norte",
        "6 ascensores",
        True,
        "Sofía Herrera",
        "11 5555-0112",
        "facilities@catalinas.ejemplo.com",
    ),
    ("Edificio Caballito Sur", "Mantenimiento mensual", False, "Luis Funes", "11 5555-0113", None),
    (
        "Sanatorio Flores",
        "Montacargas",
        True,
        "Mario Castro",
        "11 5555-0114",
        "compras@sanflores.ejemplo.com",
    ),
    (
        "Consorcio Corrientes 4100",
        "Administración Ibarra",
        True,
        "Elena Ibarra",
        "11 5555-0115",
        None,
    ),
    ("Edificio Villa Urquiza", "1 ascensor", False, "Raúl Medina", None, None),
    (
        "Centro Comercial Devoto",
        "Escaleras mecánicas",
        True,
        "Paula Vera",
        "11 5555-0117",
        "operaciones@devoto.ejemplo.com",
    ),
    (
        "Consorcio Pueyrredón 900",
        "Administración Ibarra",
        True,
        "Elena Ibarra",
        "11 5555-0115",
        None,
    ),
    (
        "Edificio Núñez Plaza",
        "Mantenimiento mensual",
        True,
        "Tomás Ortiz",
        "11 5555-0119",
        "tortiz@ejemplo.com",
    ),
    (
        "Residencia Los Robles",
        "Ascensor geriátrico",
        True,
        "Gloria Núñez",
        "11 5555-0120",
        "admin@losrobles.ejemplo.com",
    ),
    (
        "Consorcio Scalabrini 1200",
        "Administración Pérez",
        False,
        "Marta Pérez",
        "11 5555-0101",
        "admin.perez@ejemplo.com",
    ),
    ("Edificio Almagro Uno", "Mantenimiento mensual", False, "Inés Romero", None, None),
    (
        "Hospital Italiano Anexo",
        "Montacargas",
        True,
        "Federico Luna",
        "11 5555-0123",
        "compras@anexo.ejemplo.com",
    ),
    (
        "Consorcio Boedo 850",
        "Administración Sosa",
        True,
        "Laura Sosa",
        "11 5555-0103",
        "lsosa@ejemplo.com",
    ),
    ("Edificio Saavedra Park", "2 ascensores", True, "Marcos Silva", "11 5555-0125", None),
]

# client index, days from REFERENCE to the due date, amount, paid (days after due) or None
INVOICES = [
    (0, -40, "180.000,00", 5),
    (0, -10, "180.000,00", None),
    (0, 20, "180.000,00", None),
    (1, -25, "245.500,00", None),
    (1, 5, "245.500,00", None),
    (2, -5, "320.000,00", 0),
    (2, 25, "320.000,00", None),
    (3, -18, "150.000,00", None),
    (3, 12, "150.000,00", None),
    (4, -3, "198.000,00", None),
    (4, 27, "198.000,00", None),
    (5, -30, "410.000,00", 2),
    (5, 0, "410.000,00", None),
    (6, -12, "560.000,00", None),
    (6, 18, "560.000,00", None),
    (7, -45, "135.000,00", None),
    (7, 15, "135.000,00", None),
    (8, 2, "172.000,00", None),
    (9, -8, "220.000,00", 1),
    (9, 22, "220.000,00", None),
    (10, -20, "128.500,00", None),
    (11, -15, "890.000,00", 3),
    (11, 15, "890.000,00", None),
    (12, 6, "165.000,00", None),
    (13, -60, "305.000,00", None),
    (13, 1, "305.000,00", None),
    (14, -2, "142.000,00", None),
    (15, 9, "98.000,00", None),
    (16, -35, "1.250.000,00", 10),
    (16, -5, "1.250.000,00", None),
    (17, 4, "118.000,00", None),
    (18, -22, "210.000,00", None),
    (19, 3, "275.000,00", None),
    (20, -9, "112.000,00", None),
    (21, 30, "89.500,00", None),
    (22, -14, "480.000,00", 4),
    (22, 16, "480.000,00", None),
    (23, -1, "155.000,00", None),
    (24, 8, "230.000,00", None),
    (24, -28, "230.000,00", 7),
]


def dmy(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def rows() -> list[list[str]]:
    cuits = {i: cuit("30", 71000000 + i * 1013) for i, client in enumerate(CLIENTS) if client[2]}
    lines = []
    for number, (index, due_in, amount, paid_after) in enumerate(INVOICES, start=1201):
        name, subtitle, _, contact, whatsapp, email = CLIENTS[index]
        due = REFERENCE + timedelta(days=due_in)
        paid = paid_after is not None
        lines.append([
            name, subtitle, cuits.get(index, ""), contact, whatsapp or "", email or "",
            "A" if index in (5, 6, 11, 16, 22) else "B", "3", str(number),
            dmy(due - timedelta(days=10)), dmy(due), amount, "ARS",
            f"Mantenimiento de ascensores {due.strftime('%m/%Y')}",
            "pagada" if paid else "pendiente",
            dmy(due + timedelta(days=paid_after)) if paid else "",
            ("transferencia" if index % 2 else "mercado pago") if paid else "",
        ])  # fmt: skip
    return lines


def error_rows(good: list[list[str]]) -> list[list[str]]:
    """Rows 2–32 (the header is row 1): row 7 has an invalid CUIT, 12 no due date, 20 a date
    in another format, 31 an amount in words; row 9 repeats row 3's paid invoice as pending
    (a warning, not an error)."""
    lines = [list(row) for row in good[:31]]
    paid = next(row for row in lines if row[14] == "pagada")
    lines[1] = list(paid)  # row 3: a paid invoice
    lines[7] = list(paid)  # row 9: the same invoice, now "pendiente"
    lines[7][14], lines[7][15], lines[7][16] = "pendiente", "", ""
    lines[5][2] = "30-71234567-8"  # row 7: wrong check digit
    lines[10][10] = ""  # row 12: no due date
    lines[18][10] = "30.11.2026"  # row 20: not dd/mm/aaaa
    lines[29][11] = "ciento veinte mil"  # row 31: not a number
    return lines


def write_csv(path: Path, lines: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\r\n")
        writer.writerow(COLUMNS)
        writer.writerows(lines)


def write_xlsx(path: Path, lines: list[list[str]]) -> None:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.title = "Facturas"
    sheet.append(list(COLUMNS))
    for line in lines:
        sheet.append(line)
    book.save(path)


def main() -> None:
    good = rows()
    write_csv(HERE / "facturas.csv", good)
    write_xlsx(HERE / "facturas.xlsx", good)
    write_csv(HERE / "facturas-con-errores.csv", error_rows(good))
    print(f"{len(good)} invoices for {len(CLIENTS)} clients.")


if __name__ == "__main__":
    main()
