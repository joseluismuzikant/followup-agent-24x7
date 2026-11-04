# Claude Code prompts — Day 7: WhatsApp self-connection, backoffice, deploy

Day 7 is two prompts. Run them in order, each in its own Claude Code session and branch:

- **7A** (`feature/day-7a`): Embedded Signup, connection health, translated Meta errors,
  audit log, suspend, and the S8/S9 backoffice. Testable locally.
- **7B** (`feature/day-7b`): production deploy on the Oracle VM with Supabase, migrations
  on deploy, backups, and the production checks. Needs the VM, domain, Supabase project and
  Meta app ready (see the checklist at the end of this file).

Create each branch yourself first. Claude will not commit anything.

---

## Prompt 7A — WhatsApp self-connection, health and backoffice parity

```text
You are working in the followup-agent-24x7 monorepo on Day 7 (part A) of
docs/roadmap-mvp.md. Part B (deploy) is a separate session: do not build deploy files now.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- You MAY run read-only git commands (git status, git diff, git log).
- Leave every change uncommitted in the working tree. I review the diff and commit myself.
- At the end, give me a suggested commit split (files per commit + message), but do not run it.

READ BEFORE PLANNING
README.md, ARCHITECTURE.md, docs/roadmap-mvp.md (Day 7), docs/screens-spec.md (S4, S5, S8,
S9). Then: packages/core/src/followup_core/messaging (connection, pipeline, graph client,
repositories), packages/core/src/followup_core/tenancy (tenant, onboarding, setup_checklist,
setup_facts), packages/core/src/followup_core/scheduling, apps/inmo24x7/api/src/
inmo24x7_api/{whatsapp,webhooks,worker,container,main,auth,config}.py, scripts/seed_dev.py,
apps/inmo24x7/web/src (onboarding step 4, configuracion, AppShell, RequireProfile) and
apps/inmo24x7/backoffice/src (pages, WhatsAppConnection, tenants-table).

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, the domain imports nothing outward,
container.py is the composition root, errors are stable codes {"code": "..."} mapped to
Spanish in the frontends, generated OpenAPI client (regenerate schema.ts), shared
presentational components in @followup/ui, Alembic migrations only (and the single-head
rule: add a product merge revision after any core revision). Code and docs in English; UI
copy in Spanish (Argentina, voseo). Never log tokens, message text, phones or emails.

=====================================================================
1. EMBEDDED SIGNUP (S4) — the customer connects their own number
=====================================================================
Use Embedded Signup v4 (v2 and v3 were deprecated on 2026-10-15). Before coding, read the
current Meta pages "Embedded Signup implementation" and "Onboarding business customers as a
Tech Provider or Tech Partner" and follow them where they differ from this prompt; tell me
in the plan what differed.
- Web (wizard step 4 and a new Configuración → WhatsApp section, one shared component):
  load the Facebook JS SDK, FB.init with META_APP_ID and the Graph API version, and on
  "Conectar WhatsApp" call FB.login with config_id = META_EMBEDDED_SIGNUP_CONFIG_ID,
  response_type "code", override_default_response_type true, extras { setup: {} }.
  Listen for window "message" events from origins ending in facebook.com with type
  WA_EMBEDDED_SIGNUP: on FINISH keep phone_number_id, waba_id and business_id; on CANCEL
  record data.current_step (and any error_message / error_code) and show a Spanish message;
  treat FINISH_ONLY_WABA as "falta elegir el número". The code from the FB.login response
  lives 30 seconds: send it to the API together with the event data immediately.
- API POST /whatsapp/embedded-signup (owner or manager) — one use case, idempotent per
  tenant, each step recorded so "Reintentar configuración" can resume from the failed step:
  1. exchange the code for the business token (GET oauth/access_token with client_id,
     client_secret, code) — never logged, stored encrypted as on Day 5;
  2. subscribe the app to the customer's WABA (POST /{waba_id}/subscribed_apps);
  3. register the phone number (POST /{phone_number_id}/register, messaging_product
     whatsapp, a random 6-digit PIN generated per tenant and stored encrypted);
  4. read the phone number (display number, verified name, quality rating, name status) and
     store the connection as connected;
  5. return the S4 status card data. The "Mensaje de prueba" row: tell the user to send any
     message to their number from another phone; it turns green when that inbound arrives
     (inbound opens the service window; then the agent replies, which is the real test).
  A phone_number_id already connected to another tenant → 409 whatsapp_phone_number_taken.
- Subscribe the app to the account_update webhook field (document it) and handle those
  events: update the connection (e.g. disconnected, banned, business verification changes).
- S4 status card (Cuenta de Meta, Número, Recepción de mensajes, Mensaje de prueba) with
  live states, and "Pendiente en Meta" with links: "Verificar tu empresa" (Meta Business
  Settings security center) and "Cargar un medio de pago" (WhatsApp Manager →
  business.facebook.com/wa/manage/home/). Show business verification as pending/done when
  the Graph API exposes it for the business; otherwise show both links with neutral copy.
  Plug the meta_business_verified setup fact provider.
- Keep the Day 5 manual connection in the backoffice as the fallback while Tech Provider
  approval is pending; both paths write the same connection.
- Stretch (only if the rest is done): at the end of the wizard, a wa.me link and a QR to
  message the connected number ("Escribile a tu agente").

=====================================================================
2. META ERRORS IN SPANISH AND CONNECTION HEALTH
=====================================================================
- One module that maps Meta error codes/subcodes to stable internal codes and Spanish
  messages for customers (plain language + what to do) and a short technical line for
  admins. Build it from Meta's error code reference for every code the signup, register,
  subscribe, send and template calls can return; include at least the S4 example ("Ese
  número ya está registrado en otra cuenta. Eliminalo de la app de WhatsApp o elegí otro
  número, y volvé a intentar.") and S9's code 190 ("El permiso de Meta venció" — "El cliente
  quitó el acceso de la app en su cuenta de Meta."). Unknown codes → a generic message, the
  code shown to admins only. A test per mapped code.
- Health: a send or Graph call failing with an auth error (190 and the permission codes)
  marks the connection error immediately with the code, the time messages stopped and the
  last successful inbound; a scheduled job every 6 hours per connection reads the phone
  number and records status and quality rating; account_update events update it too.
- The panel shows a red banner on Inicio and Configuración when the connection is in error,
  with the translated message and "Volver a conectar" (re-runs Embedded Signup).
- The agent and senders never retry auth errors in a loop: one failure, connection error,
  queued sends wait (status waiting_connection) and resume when reconnected.

=====================================================================
3. AUDIT LOG, SUSPEND, PLAN USAGE
=====================================================================
- Audit log in core Tenancy: audit_events (tenant_id, at, actor kind user|admin|system,
  actor profile id, action, details JSONB with ids, counts and codes only — no personal
  data). Record at least: sign-up, agent config saved (version), properties imported
  (counts), WhatsApp connected / disconnected / error (code), webhook or send failures
  (system, deduplicated per hour), tenant suspended / reactivated, reconnect link sent.
- Suspend / reactivate (admin, with a reason): a suspended tenant's panel API answers 403
  tenant_suspended (except /me), the panel shows "Tu cuenta está suspendida. Escribinos a
  {soporte}." and sign-out; inbound WhatsApp messages are stored but never answered, no
  emails, no scheduled jobs for that tenant. Reactivating resumes everything. Tests.
- Plans, read-only: trial ("Prueba · N días", from trial_ends_at) and pro, with a monthly
  conversations allowance of 1,000. Conversations this month = threads with at least one
  inbound message this month on a real channel. Display only, no enforcement today.

=====================================================================
4. BACKOFFICE PARITY (S8, S9) AND SYSTEM HEALTH
=====================================================================
- Nav: Negocios, Simulador, Salud del sistema, Planes (Conversaciones stays out: Post-MVP).
- S8 Negocios: KPI cards Activos, En prueba, Onboarding sin terminar, WhatsApp con problemas;
  search by business name or owner email; filters Todos, Necesitan ayuda (WhatsApp in error,
  onboarding unfinished for more than 48 hours, or trial ending within 3 days without
  WhatsApp), En prueba; columns business + owner email, plan, onboarding "N de 5" (S9's five:
  cuenta, agente configurado, agente probado, WhatsApp conectado, propiedades propias),
  WhatsApp status (Conectado, Verificación pendiente, Acción requerida, Sin conectar),
  consultas (7 días), alta; "Dar de alta un negocio" stays.
- S9 Detalle del negocio: header (name, plan, alta, owner email), "Probar su agente",
  "Suspender"/"Reactivar"; WhatsApp card with the translated diagnosis, since when messages
  fail, "Código de Meta: N · ver detalle técnico", number, WABA (masked •••• last 4),
  business verification, last message received; actions "Enviarle link para reconectar"
  (emails the owner a link to Configuración → WhatsApp), "Reintentar configuración" (resumes
  the signup steps), "Enviar mensaje de prueba", and the manual connection form; Actividad
  (latest 20 audit events with actor and time); Onboarding checklist; Plan (conversations
  this month "N de 1.000", users count); Usuarios (name/email and role). "Cambiar plan" is
  shown disabled with "Próximamente".
- Salud del sistema: jobs by status and kind (queued, running, dead in the last 24 h, oldest
  queued age), webhooks received in the last hour, signature rejections in the last 24 h,
  failed sends in the last 24 h by Meta code, API version and commit, database check.
  Admin endpoint /admin/system.
- Planes: read-only list of the two plans and how many tenants are on each.
- Seed: add tenants in the states S8 shows (trial with WhatsApp, onboarding 2 de 5, WhatsApp
  in error with code 190, suspended), with audit events, so every filter and badge has data.

TESTS (all must pass; the Graph API is mocked at the HTTP level)
- Embedded Signup use case: happy path, each step failing and resuming, idempotency, phone
  taken by another tenant, code exchange failure, CANCEL/FINISH_ONLY_WABA handling in the web.
- Error mapping table tests; health transitions (auth error → error state, sends wait,
  reconnect resumes them), the 6-hour health job, account_update events.
- Audit events written for each action; no personal data in details.
- Suspend: panel 403s, no agent replies, no emails, reactivation.
- Backoffice endpoints: admin only, KPIs and "Necesitan ayuda" rule, search, detail payload,
  masked WABA, system health numbers.
- Frontend: S4 component states (idle, connecting, connected, error with translated
  message), Configuración WhatsApp section, error banner, suspended screen, S8 filters and
  badges, S9 cards and actions, Salud del sistema.
- Run everything CI runs: uv run ruff check ., uv run ruff format --check ., uv run pyright,
  uv run alembic upgrade head, uv run --all-packages pytest, schema regeneration + git diff
  check, pnpm lint, pnpm typecheck, pnpm test. Fix failures; do not skip or xfail tests.

CONFIG AND DOCS
- New settings: META_APP_ID, META_EMBEDDED_SIGNUP_CONFIG_ID (API and VITE_ for the panel,
  build-time for the panel), SUPPORT_EMAIL. Production requires META_APP_ID and the config id.
- README: what must exist in Meta for Embedded Signup (Tech Provider, Facebook Login for
  Business configuration with the WhatsApp Embedded Signup variation and its config id, the
  panel's domain in the app's allowed domains, the account_update and messages webhook
  fields, and that the SDK only runs on HTTPS pages, so locally it needs a tunnel to 5173);
  how to test locally with the manual fallback.
- ARCHITECTURE.md: the signup steps and resumption, health states, audit log, suspension.
- docs/roadmap-mvp.md: mark Day 7A done or note what moved.

OUT OF SCOPE
Deploy, backups and production config (7B), plan changes and billing, the cross-tenant
Conversaciones viewer, inviting users.

PROCESS
1. Plan first (use plan mode): what you found in Meta's current docs, migrations, use cases
   and endpoints with error codes, the error mapping approach, the health job, the web and
   backoffice screens, the seed additions, open questions. Wait for my OK.
2. Implement in this order: audit log and suspend, Embedded Signup and errors, health,
   backoffice, web, seed.
3. Finish with what changed, how to test locally, what needs the real Meta setup, what you
   deferred, and the suggested commit split. Do not commit.
```

---

## Prompt 7B — production deploy (Oracle VM + Supabase), backups and go-live checks

Run after 7A is merged.

```text
You are working in the followup-agent-24x7 monorepo on Day 7 (part B) of
docs/roadmap-mvp.md: deploy inmo24x7 to production. Part A is merged.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- Do NOT connect to my server, my Supabase project or Meta, and do not run anything against
  production. You write the files and the runbook; I run them.
- Leave every change uncommitted. End with a suggested commit split; do not run it.

READ BEFORE PLANNING
README.md (Images, Production migrations, env tables), ARCHITECTURE.md, the three
Dockerfiles, .github/workflows/ci.yml, apps/inmo24x7/api/src/inmo24x7_api/{config,
database,container,main,worker}.py, migrations/env.py, alembic.ini, scripts/.

PART 0 — 7A follow-ups (do these first)
0.1 apps/inmo24x7/web/src/lib/facebook.ts accepts any origin that ends with "facebook.com",
    so https://evilfacebook.com passes. Parse the origin with URL and accept only https with
    hostname facebook.com or a subdomain of it (hostname === "facebook.com" or ends with
    ".facebook.com"). Tests for both accepted forms and for look-alikes (evilfacebook.com,
    facebook.com.evil.com, http://www.facebook.com).
0.2 Owner claims: the first sign-up with an email joins the business an admin created for
    it, so that email must be proven. Read which claims Supabase access tokens carry for a
    confirmed email (check the current Supabase docs; do not guess) and only honour a claim
    when the token shows a confirmed email; otherwise sign-up creates a new business as
    usual. Tests with the fake verifier for confirmed and unconfirmed tokens. In the go-live
    runbook, require "Confirm email" on and password sign-ups off in Supabase Auth (we only
    offer Google and magic link).

TARGET
- One Oracle Cloud ARM VM (Ubuntu, São Paulo), Docker + Compose, images from GHCR (CI
  already builds amd64 + arm64 on master). Services: api, worker, web, backoffice and a
  Caddy reverse proxy with automatic HTTPS for api.<domain>, app.<domain>, admin.<domain>.
- Supabase (São Paulo): Postgres for the data, Supabase Auth (Google + magic link).
- Keep the deploy files provider-agnostic (any Linux VM with Docker), because the fallback
  for missing Oracle capacity is another VM.

SUPABASE — DATABASE
- Connection: the VM uses the Supavisor SESSION pooler (port 5432, IPv4 on every plan) or the
  direct connection if the VM has IPv6 or the project has the IPv4 add-on. Never the
  transaction pooler (6543): the shared pooler does not support prepared statements or
  pipelining in transaction mode, and the LangGraph checkpointer and psycopg rely on them.
  Add a startup check that refuses a DATABASE_URL on port 6543 with a clear message, and
  document both options with sslmode=require.
- Security, critical: Supabase exposes the public schema through its Data API with the anon
  key, which is public in our panel bundle. We do not use the Data API. Do all of:
  1. document "Enable Data API: off" in the Supabase dashboard as a required step;
  2. a migration that revokes all privileges on our tables, sequences and functions from the
     anon and authenticated roles, revokes the default privileges for future objects, and
     enables row level security on every table (no policies), including the LangGraph
     checkpoint and Alembic tables; guarded so it runs on plain local Postgres where those
     roles do not exist;
  3. a test that fails if any table in public lacks RLS (so future migrations cannot forget).
  Confirm the role our API connects with still has full access (table owner).
- Pool sizes: API and worker engine pool sizes from settings with conservative defaults that
  fit the Supabase plan's connection limit; document the math.

SUPABASE — AUTH
- Document: Site URL https://app.<domain>; redirect URLs for app. and admin.; the Google
  provider (Google Cloud OAuth client, authorized redirect URI from Supabase); custom SMTP
  for Auth emails (the built-in sender is rate-limited and not for production); the magic
  link email template in Spanish.
- API verifies tokens with SUPABASE_JWKS_URL (asymmetric signing keys) and the issuer check;
  AUTH_MODE=supabase; production refuses AUTH_MODE=dev (already).

DEPLOY FILES (new deploy/ folder)
- deploy/compose.prod.yml: the five services, images pinned by IMAGE_TAG (sha-<commit>),
  restart policies, healthchecks (API /health/ready), the worker as the API image with its
  worker command, log rotation, no published ports except Caddy 80/443, an internal network.
- deploy/Caddyfile: the three hosts, automatic TLS, security headers (HSTS, frame-ancestors,
  referrer policy, a CSP that allows the Facebook SDK on app.), gzip/zstd, request size limit
  for property imports (6 MB), and the webhook path passed through untouched.
- deploy/.env.production.example: every production variable with a comment (no real values):
  APP_ENV, DATABASE_URL, CORS_ORIGINS, PANEL_URL, AUTH_MODE, SUPABASE_URL, SUPABASE_JWKS_URL,
  LLM_MODEL and key, LANGSMITH_* (sampling), META_*, WHATSAPP_*, TOKEN_ENCRYPTION_KEY, SMTP_*,
  EMAIL_FROM, SUPPORT_EMAIL, backup settings. The real file lives only on the VM, chmod 600.
- deploy/deploy.sh <sha>: pull the images for that tag, run `alembic upgrade head` once as a
  one-off container and stop on failure, then `up -d`, wait for /health/ready, print the
  version; on failure roll back to the previous tag (stored in a file) without touching
  migrations, and say so. Idempotent.
- deploy/bootstrap.md + deploy/bootstrap.sh for a fresh VM: Docker and the compose plugin,
  a deploy user, SSH keys only, UFW/iptables allowing only 22, 80 and 443 — note that Oracle
  Ubuntu images ship iptables rules that block 80/443 and the VCN security list must also
  allow them — unattended security upgrades, swap if the VM is small, timezone UTC.
- CI: the web and backoffice images must be built with VITE_AUTH_MODE=supabase,
  VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_URL, VITE_META_APP_ID and the signup
  config id from repository variables; fail the build if any is missing on master. Add an
  optional manual workflow (workflow_dispatch) that deploys a given sha over SSH using
  environment secrets, disabled until I add them.

BACKUPS
- A backup container or systemd timer on the VM: daily pg_dump (custom format) of the
  Supabase database with a pg_dump client version >= the server's, encrypted (age or gpg with
  a public key in the env), uploaded to Oracle Object Storage through its S3-compatible API
  (rclone or the AWS CLI), 14 daily + 8 weekly kept, with a log line and a non-zero exit on
  failure. Note that the Supabase plan's own backups do not replace this.
- deploy/restore.md + restore.sh: restore a chosen dump into a scratch database and run a
  smoke query; include a "restore drill" I run once after go-live.

LOCAL PRODUCTION REHEARSAL (deploy/rehearsal.md + a script)
Before the first real deploy I run the production setup on my own machine, so deploy,
migration and proxy problems show up there first:
- the same deploy/compose.prod.yml with an override file that adds a local Postgres 17
  service (standing in for Supabase), Mailpit for SMTP, and Caddy with `tls internal` on
  api.localhost, app.localhost and admin.localhost;
- images built locally from the current tree for my machine's architecture, tagged like CI
  (sha-<commit>), with the production VITE_ build args pointing at the .localhost hosts;
- AUTH_MODE=supabase cannot work without Supabase, so the rehearsal uses the local Supabase
  CLI stack from Day 4 for auth (document the values), or, if that is not running, stops
  with a clear message: never AUTH_MODE=dev under APP_ENV=production;
- WHATSAPP_SENDER=log, the fake LLM allowed only through a REHEARSAL=true flag that the
  production config otherwise refuses (and that is never set in .env.production.example);
- the script runs deploy/deploy.sh against it, then a smoke test: /health/ready over HTTPS,
  the panel and backoffice load, the RLS migration applied, a signed simulated webhook
  answered by the worker, a backup + restore into a scratch database;
- a teardown command that removes the rehearsal containers and volumes.
Document how to trust Caddy's local CA in the browser, or to accept the warning.

GO-LIVE RUNBOOK (docs/go-live.md)
Ordered checklist I follow, with the exact values to set: DNS records; VM bootstrap; Supabase
project settings (Data API off, Auth URLs, Google, SMTP, JWKS); GitHub variables for the
image builds; .env.production on the VM; first deploy; Meta app settings (callback
https://api.<domain>/webhooks/whatsapp, verify token, webhook fields messages and
account_update, allowed domains for the SDK, Embedded Signup config, app in Live mode);
creating the first platform admin (scripts/make_admin.py run once in the API container);
the backup timer and the restore drill; and the Day 7 "Done when" test with a stopwatch:
a brand-new account from sign-up to a working agent on WhatsApp in under 10 minutes.
Also a 3-minute demo script (what to show, in order) for the recording.

TESTS
- Config: production refuses the transaction pooler port, AUTH_MODE=dev, missing required
  variables; the pool size settings.
- The RLS/privileges migration on local Postgres (no Supabase roles) and the "every table has
  RLS" test.
- Shell scripts pass shellcheck; compose file validates (`docker compose config`) with the
  example env; the Caddyfile validates (`caddy validate` in a container) if Docker is
  available, otherwise say so.
- Run everything CI runs and fix failures.

DOCS
- README: replace the "Images" and production sections with a pointer to docs/go-live.md and
  deploy/; update the architecture diagram (Supabase and the deploy are no longer planned).
- docs/roadmap-mvp.md: mark Day 7 done once I confirm the Done-when in production; until then
  note "7B ready to deploy".

PROCESS
1. Plan first (use plan mode): Part 0, file list, the database connection decision, the RLS
   migration, the deploy and rollback flow, backups, the rehearsal, CI changes, open
   questions. Wait for my OK.
2. Implement Part 0 first, then run every check you can locally, including the rehearsal if
   Docker is available (say what you could not run).
3. Finish with what changed, the go-live steps I must do in order, what you could not
   validate, and the suggested commit split. Do not commit.
```

---

## Your checklist before 7B (things only you can do)

| What | Where | Needed for |
| --- | --- | --- |
| Domain with DNS you control (api., app., admin.) | Your registrar | HTTPS, Meta webhook |
| Oracle Cloud ARM VM in São Paulo, with ports 80/443 open in the VCN security list | Oracle Cloud | Hosting |
| Object Storage bucket + S3-compatible access keys | Oracle Cloud | Backups |
| Supabase project in São Paulo; turn off the Data API | Supabase | Database and sign-in |
| Google OAuth client (web) | Google Cloud Console | "Continuar con Google" |
| Transactional email provider with SMTP (for Supabase Auth and lead emails) | e.g. Resend, Brevo, Amazon SES | Magic links, new-lead emails |
| Meta business verification approved, Tech Provider, Embedded Signup configuration (config id) | Meta Business / App Dashboard | Customers connecting their own numbers |
| `confirmacion_visita` template approved | WhatsApp Manager | Confirming visits after 24 h |
| LLM key with enough balance for production | Your LLM provider | The agent |
