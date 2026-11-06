# Claude Code prompt — Day 8: Cuentas Claras skeleton, clients and invoices

Create the branch yourself first (`git checkout -b feature/day-8`), open Claude Code at the
repo root, and paste everything inside the block. Claude will not commit anything.

```text
You are working in the followup-agent-24x7 monorepo on Day 8 of docs/roadmap-mvp.md: the
first day of the second product, Cuentas Claras ("Cobrá sin reclamar."). inmo24x7 (Days 1–7C)
is complete and must keep working exactly as it does: all its tests stay green.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub. Do not connect to any production system.
- You MAY run read-only git commands (git status, git diff, git log).
- Leave every change uncommitted. End with a suggested commit split; do not run it.

READ BEFORE PLANNING
README.md, ARCHITECTURE.md, docs/roadmap-mvp.md (Days 8–12), docs/screens-spec.md (C1, C2,
"Cuentas Claras — Clientes", C5), apps/cuentas-claras/README.md. Then how inmo24x7 is built,
because Cuentas Claras reuses it: packages/core (tenancy: tenant, onboarding,
setup_checklist, setup_facts, sign_up, admin_tenants, audit, plans; identity; scheduling;
messaging/domain/phones.py), apps/inmo24x7/api/src/inmo24x7_api (main, container, config,
auth, http_errors, logging, middleware, observability, worker, properties/ import code,
billing/), migrations/env.py, alembic.ini, the migration single-head test, scripts/dev.py,
scripts/seed_dev.py, scripts/generate_types.py, .github/workflows/ci.yml, deploy/,
packages/ui, packages/observability, packages/api-client-inmo24x7, and apps/inmo24x7/web/src
(lib/auth*, lib/dev-session, lib/api-errors, components/RequireProfile, AppShell,
ResumeOnboarding, SetupChecklist, onboarding/, pages/ingreso, pages/onboarding) and
apps/inmo24x7/backoffice/src.

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, the domain imports nothing outward,
each product API is its composition root, errors are stable codes mapped to Spanish,
generated OpenAPI clients, shared presentational components in @followup/ui, Alembic
migrations only, RLS and revoked anon/authenticated privileges on every new table (the 7B
test must keep passing), no personal data in logs, Sentry, LangSmith or audit details. Code
and docs in English; UI copy in Spanish (Argentina, voseo). If both products need a piece,
it goes to a shared package; never copy-paste a module from inmo24x7 into Cuentas Claras.

=====================================================================
PART 0 — Two products on one platform (do this first, inmo24x7 must stay green)
=====================================================================
Today the platform assumes a single product. Fix these assumptions in core, with migrations
that backfill existing rows as inmo24x7:
0.1 Tenants belong to a product: tenants.product (inmo24x7 | cuentas_claras), NOT NULL;
    slugs unique per product. Every product API knows its own product and only ever sees
    its own tenants (sign-up, /me, admin lists, seeds, jobs). Tests that tenant lists and
    lookups never cross products.
0.2 Profiles are per product: the same Supabase user (same email) can own a business in each
    product. Today profiles.id is the user id and profiles.email is globally unique. Change to
    a profile per (user_id, product): keep the existing profile ids (backfill user_id = id,
    product = inmo24x7) so every foreign key keeps working; unique (user_id, product) and
    (email, product); current_profile looks up by token user id + the API's product.
    Platform admins are admins per product profile. The dev verifier keeps mapping an email
    to the same user id in both products. Tests: one email, two products, two profiles; an
    inmo24x7 token never reaches a Cuentas Claras tenant.
0.3 Onboarding steps and the setup checklist are defined by the product, not hard-coded in
    core: core keeps the rules (forward-only, resume, completed timestamps), each product
    supplies its ordered steps and its checklist items with their fact providers. inmo24x7
    keeps exactly its current steps and items.
0.4 Job queues per product: jobs.queue (backfill inmo24x7); enqueue sets it from the
    product; each product's worker claims only its own queue; recurring core jobs (purge,
    health sweep) are enqueued per product. Test: a Cuentas Claras worker never claims an
    inmo24x7 job.
0.5 Migrations for several products: every core revision currently needs an inmo24x7 merge
    revision, and a second product would double that. Propose in the plan the cleanest
    scheme that keeps one database and one alembic.ini, for example named branches (core,
    inmo24x7, cuentas_claras) where product revisions declare depends_on the core revision
    they need and deploys run `alembic upgrade heads`, with a test asserting exactly one head
    per branch and that every product branch depends on core. Keep the existing history
    valid (no rewriting applied revisions), update deploy/deploy.sh, scripts and docs to the
    new command, and replace the single-head test with the new rule.
0.6 Shared backend pieces move out of the inmo24x7 API into a shared Python package (or core,
    justify the choice): settings base, logging, request context middleware, http error
    handlers, auth dependencies, Sentry setup and scrubbing, LangSmith tracing setup, the
    CSV/XLSX table reader from the property import, the LLM price book and usage recorder,
    and the worker loop. inmo24x7 imports them from there with no behaviour change.
0.7 Shared frontend pieces move into a new package @followup/app-shell: Supabase and dev auth
    (AuthProvider, adapters, dev session), RequireAuth/RequireProfile/ResumeOnboarding, the
    Ingreso screen and the backoffice admin gate (parameterized by product name, tagline and
    copy), the wizard frame, the setup checklist card, the API client factory with the
    bearer token and request id, and the base Spanish error-code map. inmo24x7's web and
    backoffice use it with no visible change.
0.8 CI fix — the images job fails every merge to master until go-live. Today it checks the
    production build variables (INMO24X7_API_URL, INMO24X7_PANEL_URL, SUPABASE_URL,
    SUPABASE_ANON_KEY, META_APP_ID, META_EMBEDDED_SIGNUP_CONFIG_ID) inside each matrix entry,
    exits 1 when they are missing ("Missing repository variables: …"), and the matrix's
    fail-fast cancels the other images. Missing production variables before go-live are
    expected, not a failure. Change .github/workflows/ci.yml to:
    - add a small `release-gate` job (after the python and typescript jobs, only on pushes to
      the default branch) that checks the variables per product and exposes outputs, e.g.
      inmo24x7_ready and cuentas_claras_ready (Cuentas Claras gets its own variables: API URL,
      panel URL, and the shared Supabase and Meta ones), and prints a ::notice:: listing what
      is missing and pointing to docs/go-live.md step 4 — never an error;
    - run the images job per product only when that product's gate output is true (a
      skipped job, not a failed one), with `fail-fast: false` on the matrix so one image
      failing for a real reason never cancels the others;
    - keep the real guarantee: when the gate says ready, a panel image is never built with an
      empty VITE_ value (the Dockerfile and vite.config checks stay);
    - keep tests, lint, typecheck and the schema drift check running on every push and PR,
      unaffected by the gate.
    Document in docs/go-live.md that images are only published once the variables are set,
    and in the rehearsal docs that it builds images locally and does not need them. Validate
    the workflow with actionlint if available.

=====================================================================
PART 1 — Day 8 goal
=====================================================================
Done when: in the Cuentas Claras panel (dev auth), a new user signs up, goes through the
wizard, imports docs/samples/cuentas-claras/facturas.csv and sees "Importamos N de N";
importing facturas-con-errores.csv shows the Spanish row errors and the error download;
Facturas shows the tabs with counts, search, statuses and pagination like C2; Clientes lists
the companies created by the import. The same email also signs in to inmo24x7 and sees its
own, separate business. Both backoffices list only their own product's businesses.

APPS AND TOOLING
- apps/cuentas-claras/api (FastAPI, Python package cuentas_claras_api, port 8002),
  apps/cuentas-claras/web (port 5175), apps/cuentas-claras/backoffice (port 5176), and
  packages/api-client-cuentas-claras (generated OpenAPI types + typed client).
- The Cuentas Claras worker (queue cuentas_claras) exists from today, even if it only runs
  the recurring core jobs.
- scripts/dev.py runs both products by default, with --product inmo24x7|cuentas-claras to run
  one; prints all URLs. generate_types.py and the CI drift check cover both clients.
- CI builds and tests both products; the image matrix adds cuentas-claras-api,
  cuentas-claras-web and cuentas-claras-backoffice. deploy/compose.prod.yml and the Caddyfile
  get the Cuentas Claras services behind a compose profile that stays off until Day 11
  (document the hosts it will use), and the rehearsal can include them.
- Product identity: name "Cuentas Claras", tagline "Cobrá sin reclamar.", its own accent
  color and initial "C" in @followup/ui's theme tokens (inmo24x7's look stays the same).

DOMAIN (apps/cuentas-claras/api, contexts Clients and Invoices)
- Client (the company that owes): name, subtitle (e.g. "Administración Pérez",
  "Mantenimiento mensual", shown under the name in C2), CUIT optional (11 digits, check digit
  validated, unique per tenant when present, displayed 30-12345678-9), contact name, WhatsApp
  number (normalized with core's phone module; reminders on Day 9 need it), email, notes,
  active. A client without WhatsApp is flagged ("Sin WhatsApp").
- Invoice: client, type A | B | C, point of sale (1–99999), number (1–99999999), displayed
  like ARCA: "B 0003-00001245" (point of sale padded to 4 digits, or 5 when above 9999);
  issue date, due date, amount (Decimal with 2 decimals, never float), currency ARS (USD
  allowed, displayed "USD 1.200"), description. Unique (tenant, type, point of sale,
  number).
- Status: a stored lifecycle (open, paid, cancelled; extensible so Day 9 adds promised and
  Day 10 payment_review without a redesign) and a derived display status computed in the
  tenant timezone: "Pagada · {medio}", "Vencida · N días" (due date passed), "Por vencer"
  (due within the next 7 days), "Pendiente" (later). Payment: paid_at, paid_via (manual,
  transfer, mercado_pago, other), reference. One pure, tested module for these rules.
- Manual actions (owner or manager): create and edit clients; create and edit invoices;
  "Marcar como pagada" (date, method, optional reference); "Anular" (cancel with a reason).
  Each writes an audit event (ids and counts only).

IMPORT (reuse the shared table reader from 0.6)
- One CSV/XLSX template with Spanish headers, downloadable from Facturas: cliente,
  detalle_cliente, cuit, contacto, whatsapp, email, tipo, punto_venta, numero,
  fecha_emision, vencimiento, monto, moneda (default ARS), descripcion, estado
  (pendiente | pagada, default pendiente), fecha_pago, medio_pago.
- Accept dd/mm/aaaa dates, Argentine amounts ("180.000,50", "$ 180.000", "180000"), CUIT with
  or without dashes, UTF-8 or Latin-1, comma or semicolon; max 5 MB and 5,000 rows.
- Clients are upserted by CUIT, else by normalized name; invoices by (type, point of sale,
  number). Re-importing updates open invoices; a row that would reopen a paid invoice is
  skipped with a warning ("Fila 9: la factura ya figuraba pagada; no la cambiamos.").
- Every row validated on its own; valid rows are saved even if others fail. The report: N
  importadas, N actualizadas, N omitidas, N con errores, row errors in Spanish ("Fila 7: el
  CUIT no es válido.", "Fila 12: falta el vencimiento.", "Fila 20: la fecha tiene que ser
  dd/mm/aaaa.", "Fila 31: el monto no es un número."), and a CSV download of the failed rows
  with an "error" column. Same import endpoint shape as the properties import.
- Sample files in docs/samples/cuentas-claras/: facturas.csv (about 40 invoices for ~25
  clients of an elevator-maintenance company, a mix of due dates relative to a fixed
  reference date documented in the file's README, some paid), facturas.xlsx (same data), and
  facturas-con-errores.csv (the four row errors above plus one "already paid" warning).

API (all tenant-scoped; writes need owner or manager)
- GET /invoices?tab=pending|overdue|promised|paid_this_month&q=&page= with counts per tab
  in the response ("Pendientes" = every open invoice, "Vencidas" = open and past due, "Con
  promesa" = 0 until Day 9, "Pagadas este mes" = paid this calendar month in the tenant
  timezone); q matches client name, CUIT digits and invoice number in any format ("1245",
  "0003-00001245", "B 3-1245"); page size 25; each row carries the display status, days
  overdue and "next_action" (null today; Day 9 fills it).
- GET/POST/PATCH /invoices/{id}, POST /invoices/{id}/mark-paid, POST /invoices/{id}/cancel.
- GET/POST/PATCH /clients, GET /clients?q=&missing_whatsapp=, with open invoices count and
  amount owed per client.
- POST /invoices/import (multipart), GET /invoices/import/{id}/errors.csv,
  GET /invoices/import-template.csv.
- GET /summary for Inicio today: total a cobrar (amount and count), vencido (amount and
  count). The rest of C1 is Day 11.
- Error codes: client_not_found, client_invalid, cuit_invalid, cuit_taken, invoice_not_found,
  invoice_invalid, invoice_number_taken, invoice_already_paid, import_file_invalid,
  import_too_large.

WEB (apps/cuentas-claras/web, built on @followup/app-shell and @followup/ui)
- Ingreso with Cuentas Claras copy (tagline "Cobrá sin reclamar.", a short pitch for service
  companies that bill monthly retainers) and the dev box in dev mode.
- Wizard, five steps with progress, "Terminar después" and resume: 1 "Tu negocio" (name and
  type: Mantenimiento (ascensores, matafuegos, climatización), Seguridad y monitoreo, Soporte
  IT, Agencia con abonos, Otro servicio mensual); 2 "Tus facturas" (download the template,
  import with the report, or "Cargar después"); 3 "Recordatorios" (a read-only preview of the
  default sequence from C4 — 3 días antes, el día del vencimiento, 7 días después — with
  "Muy pronto vas a poder ajustarla.", real settings on Day 9);
  4 "Conectar" (WhatsApp and Mercado Pago cards marked "Muy pronto", Day 9); 5 "Listo".
- Nav: Inicio, Facturas, Clientes. Aprobaciones and Recordatorios y cobros are added on the
  days that build them (do not show dead links).
- Inicio: the setup checklist (cuenta, facturas cargadas, WhatsApp conectado, Mercado Pago
  conectado, recordatorios configurados; the last three false until Day 9), and two cards
  "Total a cobrar" (amount, "N facturas") and "Vencido" (amount, "N facturas"), plus
  "Importar facturas". Empty state when there are no invoices.
- Facturas (C2): "Descargar plantilla CSV", "Importar facturas" (drag and drop, report
  card), tabs with counts, search "Buscar por cliente o número de factura", columns client +
  subtitle, invoice number, amount (es-AR), due date ("10 oct"), status badge, "Lo próximo"
  ("—" today), pagination "Mostrando 1 a 25 de N", the ARCA notice "Próximamente vas a poder
  traer las facturas directo desde ARCA, sin importar archivos.". Clicking a row opens a
  detail drawer with the invoice, the client, the payment info, and the actions.
- Clientes: list with search, "Sin WhatsApp" filter and badge, open invoices and amount owed;
  create/edit form with CUIT and WhatsApp validation; client detail with its invoices.
- Configuración: business name and type, team hours (they will be the reminder send window
  on Day 9) and notification emails, reusing the core settings.

BACKOFFICE (apps/cuentas-claras/backoffice, minimal today; C5 is Day 11)
- The shared admin gate; Negocios list of Cuentas Claras businesses (name, owner email, plan,
  onboarding "N de 5", clients, open invoices amount, alta) with search; a detail page with
  plan, owner, onboarding checklist, the activity log and Suspender/Reactivar reusing the
  core admin use cases. No simulator yet (the collections agent is Day 10).

SEED AND DOCS
- seed_dev.py seeds both products: inmo24x7 exactly as today, plus Cuentas Claras:
  admin@local.test as admin of both backoffices, dueno@ascensoresdelta.test owning "Ascensores
  Delta" with the sample invoices imported through the real import use case (onboarding
  finished), and nuevo@local.test without a Cuentas Claras business to try the wizard.
  Idempotent; --reset resets both.
- README: run either or both products, ports, the new migration command, Cuentas Claras env
  variables. ARCHITECTURE.md: the multi-product model (product on tenants, per-product
  profiles and queues, product-defined onboarding, the shared packages, the migration
  branches). apps/cuentas-claras/README.md: status and structure. docs/roadmap-mvp.md: mark
  Day 8 done (with Part 0) or note what moved.

TESTS (all must pass, both products)
- Part 0: tenant and profile isolation across products; one email in both products;
  product-defined onboarding and checklist (inmo24x7 unchanged); job queues; the new
  migration rule; inmo24x7's whole suite unchanged and green.
- Domain: CUIT validation, invoice number formatting and parsing, display status and days
  overdue around midnight in Buenos Aires vs UTC, "Por vencer" boundary, mark paid and
  cancel transitions.
- Import: the sample files (CSV and XLSX), the error file's exact messages and warning,
  re-import updates and the paid-invoice skip, encodings, separators, amount and date
  formats, limits, upsert rules for clients.
- API: scoping and roles, tab counts and search formats, pagination, summary, error codes.
- Frontend: wizard steps and resume, import report and error download, Facturas tabs,
  search, badges and drawer actions, Clientes list, filter and form validation, Inicio cards,
  the Cuentas Claras Ingreso copy; inmo24x7's frontend tests still pass with app-shell.
- Run everything CI runs for both products: ruff check, ruff format --check, pyright,
  alembic upgrade (new command), pytest, both schema regenerations + drift check, pnpm lint,
  typecheck, test. Fix failures; do not skip or xfail tests.
- Then run the Done-when yourself in dev mode (dev.py --seed, both panels) and report.

OUT OF SCOPE
Reminders, scheduling rules, WhatsApp and Mercado Pago for Cuentas Claras (Day 9), the
collections agent and approvals (Day 10), the full C1 dashboard and C5 backoffice (Day 11),
deploying Cuentas Claras (Day 11), ARCA, clients-only CSV import.

PROCESS
1. Plan first (use plan mode): Part 0 in detail (migrations and backfills, the profile
   change and every place that reads profiles, the migration scheme you propose, what moves
   to which shared package), then the Cuentas Claras apps, domain, import, API shapes and
   error codes, web and backoffice screens, CI and dev tooling, seeds, and open questions.
   Wait for my OK.
2. Implement Part 0 first and run inmo24x7's full suite before starting Cuentas Claras. Then
   the API (domain, import, endpoints), then the web, then the backoffice, then CI, seeds
   and docs.
3. Finish with what changed, exact commands to run and test both products, what you
   deferred, and the suggested commit split. Do not commit.
```
