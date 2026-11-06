# Cuentas Claras sample files

Made-up data for an elevator-maintenance company: 40 invoices for 25 clients (buildings,
property managers, a clinic, a hotel…), some paid, some overdue, some due soon.

| File | What it is |
| --- | --- |
| `facturas.csv` | The template filled in: semicolons, UTF-8, `dd/mm/aaaa` dates, `180.000,00` amounts. Importing it gives "Importamos 40 de 40". |
| `facturas.xlsx` | The same rows as an Excel file. |
| `facturas-con-errores.csv` | 31 rows with four errors (row 7: invalid CUIT; row 12: no due date; row 20: a date not written dd/mm/aaaa; row 31: an amount in words) and one warning (row 9 repeats row 3's paid invoice as pending: "la factura ya figuraba pagada; no la cambiamos."). |

**Reference date: 2 November 2026.** Due dates go from 60 days before it to 30 days after
it, so the mix of "Vencida", "Por vencer" and "Pendiente" depends on when you import:

- on the reference date: 8 paid (all in October), and of the 32 open ones 13 overdue, 7 due within 7 days
  ("Por vencer") and 12 later;
- `scripts/seed_dev.py` shifts every date so that the reference date is today, which gives
  the same mix whenever you seed.

Regenerate all three files from one list (they never drift apart):

```bash
uv run --all-packages python docs/samples/cuentas-claras/make_samples.py
```

Clients without a WhatsApp number (shown "Sin WhatsApp") and without a CUIT are included on
purpose; the CUITs are made up but have a valid check digit.
