# Claude Code prompt — Day 4: local dev setup, properties and the lead agent

Create the branch yourself first (`git checkout -b feature/day-4`), open Claude Code at the
repo root, and paste everything inside the block. Claude will not commit anything.

```text
You are working in the followup-agent-24x7 monorepo on Day 4 of docs/roadmap-mvp.md.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- You MAY run read-only git commands (git status, git diff, git log).
- Leave every change uncommitted in the working tree. I review the diff and commit myself.
- At the end, give me a suggested commit split (files per commit + message), but do not run it.

READ BEFORE PLANNING
README.md, ARCHITECTURE.md, docs/roadmap-mvp.md (Days 3–6), docs/screens-spec.md (S3, S5,
S6, S7). Then the Day 3 code: packages/core/src/followup_core/conversation,
apps/inmo24x7/api/src/inmo24x7_api/{container,main,simulator,tracing}.py and leads/
(graph.py, properties.py, llm.py, display.py, prompts/), migrations/env.py, alembic.ini,
scripts/dev.py, .env.example, apps/inmo24x7/web/src (lib/supabase.ts, lib/auth.tsx,
pages/ingreso.tsx, pages/propiedades.tsx, pages/consultas.tsx, pages/probar.tsx) and
apps/inmo24x7/backoffice/src/lib.

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, the domain imports nothing outward,
container.py is the composition root, errors are stable codes {"code": "..."} mapped to
Spanish in the frontends, generated OpenAPI client (regenerate schema.ts), shared
presentational components in @followup/ui. Code and docs in English; UI copy and agent
replies in Spanish (Argentina, voseo). The tenant always comes from the caller's profile.
Database changes are Alembic migrations only, never ad-hoc SQL or create_all.

=====================================================================
PART 0 — Local development without external services
=====================================================================
Goal: after `git clone`, `cp .env.example .env` and `uv run --all-packages python
scripts/dev.py`, I can sign in to the panel and the backoffice, use the simulator and test
everything locally with only Docker. No Supabase project, no LLM key, no LangSmith.

0.1 Bug: .env.example ships `VITE_SUPABASE_URL=` and `VITE_SUPABASE_ANON_KEY=` empty. Vite
    passes them as "" and lib/supabase.ts uses `??`, so createClient("") throws and the panel
    and backoffice render a blank page. Fix both apps: treat empty strings as unset, and never
    construct the Supabase client when auth mode is dev (0.2).
0.2 Dev auth mode, development only:
    - New setting AUTH_MODE = supabase | dev (API) and VITE_AUTH_MODE = supabase | dev
      (panels). .env.example defaults both to dev.
    - API: in dev mode the token verifier accepts only tokens of the form `dev:<email>` and
      maps them to user_id = uuid5(fixed namespace, lowercased email) and that email. Any
      other token → 401. Replace today's FakeTokenVerifier default that maps every token to
      one fixed user. Keep the mapping-based fake for tests.
    - Production guard: with APP_ENV=production, AUTH_MODE=dev is a startup error. The panel
      and backoffice Vite builds fail if VITE_AUTH_MODE=dev in `vite build` with mode
      production (check in vite.config.ts), so a dev build can never ship.
    - Web and backoffice: an auth abstraction with two implementations (Supabase and dev)
      behind the existing AuthProvider/useAuth, so pages do not care which is active. In dev
      mode the Ingreso screen and the backoffice sign-in show, below the normal UI, a clearly
      marked box "Modo desarrollo" with an email field and "Entrar"; the session is the token
      `dev:<email>` kept in localStorage (wrapped in try/catch). Sign-out clears it. The
      Google and magic-link buttons are hidden in dev mode.
    - Tests: verifier accepts dev tokens and rejects others; production config rejects dev
      mode; the web guard and Ingreso render the dev box only in dev mode.
0.3 Dev seed script `scripts/seed_dev.py`, run as `uv run --all-packages python
    scripts/seed_dev.py`:
    - Refuses to run when APP_ENV=production. Idempotent (running twice changes nothing).
    - Goes through the real use cases (SignUp, SaveAgentSetup, AdvanceOnboarding, the Day 4
      property import), not raw inserts, so seeds stay valid as the domain changes.
    - Creates: admin@local.test (platform admin, with its own tenant "Plataforma"),
      dueno@inmobiliariasur.test as owner of "Inmobiliaria Sur" with default agent config,
      onboarding finished and the ~20 own properties from docs/samples/propiedades.csv;
      nuevo@local.test with no profile, to try sign-up and the wizard from scratch.
    - `--reset` drops and recreates the public schema of the DEV database (the URL must
      point to localhost or 127.0.0.1, otherwise refuse), runs `alembic upgrade head`, then
      seeds. Ask for confirmation unless `--yes`.
    - Prints the emails to sign in with in dev mode.
    - scripts/dev.py gets a `--seed` flag that runs it after migrations.
    - Keep scripts/set-platform-admin.sql, and add `scripts/make_admin.py <email>` for
      Supabase mode.
0.4 Sample files in docs/samples/: propiedades.csv (about 20 valid CABA rows), the same as
    propiedades.xlsx, and propiedades-con-errores.csv (3 bad rows matching the S7 examples:
    missing price, invalid link, invalid operation). The seed and the tests use these files.
0.5 README "Local development" section with three modes, each with exact steps:
    a) Zero external services (default): Docker + dev auth + fake LLM. Which emails to use.
    b) Local Supabase with the Supabase CLI (`supabase init`, `supabase start`): which values
       from `supabase status` go into which variable; that SUPABASE_URL must match the token
       issuer exactly (127.0.0.1 vs localhost); adding http://localhost:5173 and :5174 as
       redirect URLs in supabase/config.toml; reading magic-link emails in the local mail UI
       the CLI prints; that Google sign-in needs a Google OAuth client and is optional.
       Commit a supabase/config.toml prepared for this, if the CLI layout allows it.
    c) A Supabase cloud project (what production will use).
    Plus: how to use a real LLM (LLM_MODEL + key), how to turn on LangSmith, how to run the
    tests (Postgres must be up), and how to reset the dev database.

=====================================================================
PART 1 — Day 4 goal
=====================================================================
Done when: I import docs/samples/propiedades.csv in Propiedades and see "Importamos N de N";
importing propiedades-con-errores.csv shows the report with the 3 row errors and "Descargar
las 3 con errores". In the simulator a lead gets only MY published properties with their
real links, leaves name and contact, picks a proposed visit slot inside team hours (or asks
to talk to a person), and is handed off. The lead appears in Consultas with its status.

DATABASE
Properties and Leads are inmo24x7 contexts (ARCHITECTURE.md), so their migrations are the
FIRST product revisions in apps/inmo24x7/api/migrations/versions. The first one sets
down_revision to the current core head (check it; it should be 0006) and uses its own
revision ids (e.g. "inmo_0001"). Register the product models in migrations/env.py. Make
sure `alembic upgrade head` from the root still applies everything in order and that the
test fixture still builds the schema from migrations.

PROPERTIES (apps/inmo24x7/api/.../properties, S7)
- Domain: Property (tenant_id, title, address, operation sale|rent, zone, price, currency
  ARS|USD, rooms, link (absolute http/https URL), status published|paused, created_at,
  updated_at). Unique (tenant_id, link): re-importing the same link updates the property.
- Import: CSV (UTF-8 and Latin-1, comma or semicolon) and XLSX (openpyxl), max 5 MB and
  2,000 rows. Spanish column headers in a downloadable template: titulo, direccion,
  operacion (venta|alquiler), zona, precio, moneda (ARS|USD; default USD for venta and ARS
  for alquiler), ambientes, link, estado (publicada|pausada, default publicada). Accept
  Argentine number formats (850.000 / 850000 / USD 185.000). Validate each row
  independently; valid rows are saved even if others fail. Result: imported, updated, failed,
  and row errors in Spanish exactly like S7 ("Fila 12: falta el precio.", "Fila 30: el link
  no es una dirección web válida.", "Fila 41: la operación tiene que ser «venta» o
  «alquiler»."). The error report download is a CSV with the original failed rows plus an
  "error" column.
- Manual create and edit with the same validation; publish/pause; no hard delete (pause
  instead).
- List: search by address or zone (accent-insensitive), operation filter, status, page size
  20, and an inquiries count per property (distinct leads that were shown the property).
- Database PropertySearch adapter, tenant-scoped (add tenant_id to the port's search call),
  published properties only. Matching rules stay as today: operation, zone, rooms, budget in
  the same currency with the over-budget tolerance; no currency conversion. While the
  tenant has no published own property, keep the sample fixture and the "propiedades de
  ejemplo" banner. As soon as one exists, the fixture is never used for that tenant. Plug in
  the own_properties setup fact provider.
- Endpoints (writes need owner or manager): GET /properties, POST /properties,
  PATCH /properties/{id}, POST /properties/{id}/publish, POST /properties/{id}/pause,
  POST /properties/import (multipart) → report with an import id,
  GET /properties/import/{id}/errors.csv, GET /properties/import-template.csv. Error codes:
  property_not_found, property_invalid, property_link_taken, import_file_invalid,
  import_too_large.

LEADS (apps/inmo24x7/api/.../leads)
- Domain: Lead, one per conversation thread: tenant_id, thread key, channel, is_test (true
  for simulator threads), name, contact, the qualification answers snapshot keyed by question
  key, status, status history with timestamps, created_at, last_activity_at.
  Statuses: qualifying ("Calificando"), visit_proposed ("Visita propuesta"),
  human_requested ("Pidió hablar con alguien"), visit_confirmed ("Visita confirmada"; only
  set by the team on Day 6, defined now). Transitions are enforced in the domain.
- LeadPropertyMatch: lead_id, property_id, shown_at, so S7 inquiries and the Day 6 inbox
  can use it.
- Visit: lead_id, property_id, proposed slot, status proposed|confirmed|cancelled.
- Slot proposal is a pure domain function: the next 2 slots of 30 minutes, at least 2 hours
  from now, inside team hours (use is_within_team_hours and the tenant timezone), skipping
  past times. Out of hours, the agent still proposes slots, and the reply says the team will
  confirm (after_hours_mode).
- A lead is created when a thread receives its first inbound message, and is updated after
  every turn from the graph state (answers, name, contact).

AGENT (extend the Day 3 graph; the graph decides the flow, the LLM never does)
- Declare the tools once in a registry: search_properties, save_contact, propose_visit,
  hand_off. Each has an input schema and a handler; add the test from the roadmap that every
  declared tool has a handler, and every handler is reachable from the graph.
- Flow additions after options are shown: if the lead shows interest in a property (the
  extract step recognises which card, by position or address), call propose_visit and offer
  the two slots for that property; when the lead picks one, record the Visit (proposed), set
  the status to visit_proposed, ask for name/contact if still missing, then hand_off. If at
  any point the lead asks for a person, hand_off immediately and set human_requested.
- hand_off appends a system message "El agente derivó la consulta a tu equipo" to the
  transcript and records the status change. After a hand-off the agent keeps answering
  politely but never proposes new visits in that thread.
- save_contact validates and normalises Argentine phone numbers (+54 9 ...) and emails.
- The rules from the roadmap stay enforced in code and tested: show options before asking for
  personal data, one question per message, only real links (own properties' links, or the
  sample fixture's local pages while it is in use).
- Prompts: add new versioned files (extract.v2.md, reply.v2.md) instead of editing v1;
  log and trace the versions used. Extend FakeLlm so the full Done-when conversation runs
  deterministically.
- LangSmith: each tool call is a child run of the turn with its name; keep PII redaction.

API FOR THE PANEL (minimal; the full inbox is Day 6)
- GET /leads?status=&include_test=&page= → name or phone, what they look for (one line
  built from the answers, e.g. "Alquiler · 2 amb. · Palermo · hasta $900.000"), status,
  is_test, last activity. GET /leads/{id} → the same plus answers, visits and the transcript.

WEB
- Propiedades (S7): "Agregar una" form (dialog or page), "Importar CSV o Excel" with
  drag-and-drop, the import report card with "Descargar las N con errores", link to download
  the template, search, operation filter, status badge Publicada/Pausada with a toggle,
  columns title + address + "ver aviso", operation, zone, price (ARS or USD formatted es-AR),
  rooms, status, inquiries; pagination "Mostrando 1 a 20 de N".
- Consultas: a simple list for now with the S5 status badges and a "Prueba" badge for
  simulator leads (toggle to show or hide them), and a detail panel with the answers, the
  proposed visit and the transcript (read-only). Takeover and confirm-visit buttons are Day 6;
  do not add them.
- Simulator (wizard step 3, /probar and backoffice): render the visit-slot choice as buttons
  inside the chat (they send the slot as the visitor's message), show the hand-off system
  message, and hide the sample banner once the tenant has own published properties.
- Inicio: setup checklist "Subir tus propiedades" turns done after the first import.

TESTS (all must pass)
- Import: CSV and XLSX happy paths with the sample files, the errors file produces exactly
  the 3 S7 messages, encodings and separators, re-import updates by link, size and row
  limits.
- PropertySearch DB adapter: tenant isolation, only published, fixture fallback rule.
- Slot proposal: inside hours, skips closed days, after-hours, timezone, never in the past.
- Lead domain transitions; one lead per thread; is_test for simulator threads.
- Graph with FakeLlm: the full Done-when conversation end to end; the "talk to a person"
  path at any step; no visit proposal after hand-off; only real links; tool registry test.
- API integration: properties and leads scoping and role checks, import endpoints, the
  error CSV download, leads list filters.
- Part 0: dev verifier, production guards, seed idempotency (run twice), --reset refuses a
  non-local URL.
- Frontend: import flow and report, property form validation, publish/pause toggle, leads
  list badges, slot buttons in the simulator, dev sign-in box.
- Run everything CI runs: uv run ruff check ., uv run ruff format --check ., uv run pyright,
  uv run alembic upgrade head, uv run --all-packages pytest, schema regeneration + git diff
  check, pnpm lint, pnpm typecheck, pnpm test. Fix failures; do not skip or xfail tests.
- Then run the app yourself in dev mode with the seed and walk through the Done-when once;
  report anything that did not behave as specified.

DOCS
- ARCHITECTURE.md: product contexts Properties and Leads, product migrations chained to the
  core head, the tool registry, auth modes.
- README: the Local development section (0.5), sample files, env table (AUTH_MODE,
  VITE_AUTH_MODE).
- docs/roadmap-mvp.md: mark Day 4 done (with Part 0) or note what moved.

OUT OF SCOPE
WhatsApp (Day 5), new-lead email (Day 5), takeover, confirm visit and KPIs (Day 6),
property photos, CRM integrations.

PROCESS
1. Plan first (use plan mode): Part 0 design, the migrations (tables, columns, constraints,
   revision chain), domain models and transitions, the tool registry and graph changes, API
   shapes and error codes, web components, and open questions. Wait for my OK.
2. Implement Part 0 first, then properties, then leads and the agent, then the web.
3. Finish with what changed, exact commands to run locally, how I test the Done-when by hand,
   what you deferred, and the suggested commit split. Do not commit.
```
