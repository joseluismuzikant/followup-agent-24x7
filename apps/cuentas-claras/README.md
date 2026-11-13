# Cuentas Claras

**Tagline:** "Cobrá sin reclamar."

Invoice collection for service companies in Argentina.

## Customer

Service companies that bill a monthly retainer to between 30 and 300 business clients, and where the owner or a single admin chases payments by hand.

First segments:

- Maintenance: elevators, fire extinguishers, HVAC.
- Security and monitoring.
- IT support.
- Agencies with monthly fees.

## Problem

Payments arrive late by habit, chasing them takes hours every month, and nobody wants to be the one who pressures a client they have a relationship with.

## What it does

- Reads invoices issued through ARCA (Argentina's tax authority) and payments received in Mercado Pago, and reconciles what is paid and what is pending.
- Sends WhatsApp reminders with escalation (before the due date, on the due date, and after) including a payment link.
- Answers the usual replies: "I already paid" (asks for the receipt and verifies it), "send me the invoice", "can I pay on the 15th?".
- Payment promises and installment plans require the owner's approval with one tap.
- Shows a simple dashboard: total owed, payment promises, and money recovered this month.

## Not for

Large consumer debt collection or retail stores that charge at the counter.

## Pricing model

A base fee plus a fee per managed client, so the price grows with the customer.

## Success metric

Money recovered per month and days sales outstanding.

## Status

Scope only. It is built after inmo24x7 on the same engine. There is no code yet.

## Status

Day 8 is built: invitation-only accounts (an admin's "Dar de alta un negocio") and the five-step wizard (Tu negocio, Tus facturas, Recordatorios,
Conectar, Listo), clients and invoices with spreadsheet import, the Facturas and Clientes
screens, Inicio with "Total a cobrar" and "Vencido", Configuración, and a backoffice with the
business list and detail (suspend / reactivate).

Day 9A is built: WhatsApp (Embedded Signup and the backoffice's manual connection, shared
with inmo24x7, with Cuentas Claras's own Meta app), the reminder policy and the C4 screen
"Recordatorios y cobros", WhatsApp templates per business with Meta's status, Argentine
holidays, the planner and the send job, "Lo próximo" in Facturas, promises ("Registrar
promesa de pago"), "No enviar recordatorios" per client, the payment link page `/p/<token>`
with the transfer details, and the owner's emails (escalation, a client's reply).

Not yet: Mercado Pago (Day 9B: OAuth per business, the checkout on the payment link and its
webhook), the collections agent and approvals (Day 10), the dashboard and the rest of the
backoffice (Day 11). In the panel Mercado Pago shows as "Muy pronto". Cuentas Claras does not read ARCA: invoices come from
the business's own billing system as a CSV or Excel export.

## Structure

```text
api/                     FastAPI API (cuentas_claras_api), port 8002
  src/cuentas_claras_api/
    product.py           Product key, onboarding steps, business types, checklist facts
    clients/             Clients context (domain, application, infrastructure, router)
    invoices/            Invoices context: number, status (open, promised, paid, cancelled), import
    reminders/           Reminders: policy, calendar and holidays, planning, templates, sends
      holidays_ar.toml   extra non-sending dates (and removals) on top of the holidays package
    payments/            Payment requests (/p/<token>) and transfer details (Mercado Pago: 9B)
    whatsapp.py          templates created on connect; its own webhook counters
    backoffice/          admin queries and router
    container.py         composition root (always passes this product's key to core)
    main.py, worker.py   the app and the job worker (queue cuentas_claras)
  migrations/versions/   the cuentas_claras Alembic branch (cc_NNNN)
  tests/
web/                     the panel (@cuentas-claras/web), port 5175
backoffice/              the backoffice (@cuentas-claras/backoffice), port 5176
```

Shared pieces come from `packages/core`, `packages/platform`, `@followup/app-shell` and
`@followup/ui`; the generated client is `@followup/api-client-cuentas-claras`.

## Run it

```bash
uv run --all-packages python scripts/dev.py --seed --product cuentas-claras
```

Then sign in at http://localhost:5175 with `dueno@ascensoresdelta.test` / `local-1234` (40
sample invoices), `dueno@monitoreosur.test` / `local-1234` (suspended),
`duena@soporteitnorte.test` / `local-1234` (wizard unfinished, no invoices),
`invitado@matafuegosnorte.test` / `temporal-1234` (invited, never came in) or
`nuevo@local.test` / `temporal-1234` (invited: forced password change,
then the wizard from scratch), and at http://localhost:5176 with `admin@local.test` /
`local-1234`. The sample files are in `docs/samples/cuentas-claras/`.

## Reminders locally

The seed connects Ascensores Delta to a fake number (`dev-cc-phone-1`, log sender: nothing
reaches Meta), creates its templates already approved, saves its policy and its transfer
details. The sample invoices fall on every step (due in 3 days, today, overdue), so:

1. Start the stack (`dev.py`). On a weekday between 9 and 12 (Buenos Aires) the worker's
   morning planner sends right away; otherwise open the backoffice → Ascensores Delta →
   **Planificar ahora**, after choosing a window that is open now in Recordatorios y cobros
   (e.g. Personalizado 06:00–22:00). Reminders never go out on weekends or holidays.
2. Each reminder shows in the worker's log (`whatsapp_log_send`), in the client's
   "Lo próximo" and in C4's month count. The payment link of a sent reminder is in the
   database (`whatsapp_outbound.body`, the button's parameter): open
   http://localhost:5175/p/<token>.
3. A client's reply: `scripts/simulate_whatsapp.py --product cuentas-claras --from
   5491155550106 "Ya la pagué"`; it lands on the client's thread and the owner gets an
   email (http://localhost:8025).
4. Meta reviewing a template: `scripts/simulate_whatsapp.py --product cuentas-claras
   --template-status <meta id> REJECTED --reason INVALID_FORMAT` (the ids are in
   `cc_whatsapp_templates.meta_template_id`).
