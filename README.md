# followup-agent-24x7

## What this is

A platform of WhatsApp agents that follow up on every conversation until it reaches an outcome. One shared engine powers several products.

All repository documentation and code are in English. Product UI copy is in Spanish (Argentina).

See the [12-day MVP roadmap](docs/roadmap-mvp.md) and the [screen specifications](docs/screens-spec.md).

## The products and their business goals

### inmo24x7: never lose a lead again

- **Customer:** real estate agencies, starting with large agencies and franchise networks that receive hundreds of inquiries from listing portals.
- **Problem:** inquiries arrive at night and on weekends, answers come hours later, and most leads go cold before anyone talks to them.
- **What it does:** replies on WhatsApp in seconds at any hour, qualifies the lead (operation, area, budget, financing), suggests matching properties from the agency's own listings, books visits, and hands off to an agent with a summary.
- **Success metric:** booked visits per month.
- **Status:** the foundation (milestone 1) is implemented; the full product follows Days 1–7 of the roadmap.

### Cuentas Claras: collect without chasing

**Tagline:** "Cobrá sin reclamar."

- **Customer:** service companies in Argentina that bill a monthly retainer to between 30 and 300 business clients, and where the owner or a single admin chases payments by hand. First segments: maintenance (elevators, fire extinguishers, HVAC), security and monitoring, IT support, and agencies with monthly fees.
- **Problem:** payments arrive late by habit, chasing them takes hours every month, and nobody wants to be the one who pressures a client they have a relationship with.
- **What it does:**
  - Reads invoices issued through ARCA (Argentina's tax authority) and payments received in Mercado Pago, and reconciles what is paid and what is pending.
  - Sends WhatsApp reminders with escalation (before the due date, on the due date, and after) including a payment link.
  - Answers the usual replies: "I already paid" (asks for the receipt and verifies it), "send me the invoice", "can I pay on the 15th?".
  - Payment promises and installment plans require the owner's approval with one tap.
  - Shows a simple dashboard: total owed, payment promises, and money recovered this month.
- **Not for:** large consumer debt collection or retail stores that charge at the counter.
- **Pricing model:** a base fee plus a fee per managed client, so the price grows with the customer.
- **Success metric:** money recovered per month and days sales outstanding.
- **Status:** scope only today; it is built on Days 8–12 of the roadmap on the same engine.

### What both share

Both are follow-up agents: inmo24x7 follows a lead until a visit is booked; Cuentas Claras follows an invoice until it is paid.

| Product | Follows | Outcome | Integrations |
| --- | --- | --- | --- |
| inmo24x7 | A real estate lead | A property visit is booked | WhatsApp via Meta Cloud API; the agency's listings |
| Cuentas Claras | An invoice | The invoice is paid | WhatsApp via Meta Cloud API; ARCA; Mercado Pago |

## Screens

Selected screens from the product prototypes. Click an image to open its full gallery.

| inmo24x7 | Cuentas Claras |
| --- | --- |
| <a href="docs/inmo24-screens.html"><img src="docs/screens/inmo24x7-onboarding-simulator.png" width="480" alt="inmo24x7 onboarding chat simulator"></a> | <a href="docs/cuentas-claras-screens.html"><img src="docs/screens/cuentas-claras-panel.png" width="480" alt="Cuentas Claras collections dashboard"></a> |
| <a href="docs/inmo24-screens.html"><img src="docs/screens/inmo24x7-panel.png" width="480" alt="inmo24x7 panel home"></a> | <a href="docs/cuentas-claras-screens.html"><img src="docs/screens/cuentas-claras-approvals.png" width="480" alt="Cuentas Claras payment approvals"></a> |

Full galleries:

- [inmo24x7 screens](docs/inmo24-screens.html): sign-in, onboarding, chat simulator, WhatsApp connection, dashboard, inquiries, properties, and backoffice.
- [Cuentas Claras screens](docs/cuentas-claras-screens.html): dashboard, invoices, approvals, reminders and collections, and backoffice.

Open the gallery HTML files in a browser to browse every screen. Behavior, API, and data requirements for each screen live in the [screen specification](docs/screens-spec.md).

## Architecture

Dashed components and edges are planned. Production runs on one VM with Docker and
Supabase ([docs/go-live.md](docs/go-live.md)).

```mermaid
flowchart TB
    subgraph Channels["Channels"]
        WHATSAPP["WhatsApp<br/>Meta Cloud API"]
        SIMULATOR["Web chat simulator"]
    end

    subgraph Frontends["Frontends"]
        WEB["inmo24x7 web"]
        BACKOFFICE["inmo24x7 backoffice"]
        CC_WEB["Cuentas Claras web<br/>(planned)"]
        CC_BACKOFFICE["Cuentas Claras backoffice<br/>(planned)"]
    end

    subgraph Shared["Shared frontend packages"]
        UI["@followup/ui"]
        INMO_CLIENT["Typed API client<br/>@followup/api-client-inmo24x7"]
        CC_CLIENT["Typed API client<br/>@followup/api-client-cuentas-claras<br/>(planned)"]
    end

    subgraph APIs["Product APIs"]
        API["inmo24x7 API"]
        CC_API["Cuentas Claras API<br/>(planned)"]
    end

    subgraph Product["inmo24x7 contexts"]
        PROPERTIES["Properties<br/>import · search"]
        LEADS["Leads<br/>statuses · visits · agent tools"]
    end

    subgraph Core["packages/core"]
        TENANCY["Tenancy"]
        IDENTITY["Identity"]
        MESSAGING["Messaging<br/>webhook · sending"]
        SCHEDULING["Scheduling<br/>Postgres jobs"]
        NOTIFICATIONS["Notifications<br/>email"]
        CONVERSATION["Conversation"]
    end

    PORT["AgentRuntime port"]
    LANGGRAPH["LangGraph runtime"]
    CHECKPOINTER["Postgres checkpointer"]
    LLM["LLM port<br/>Anthropic · OpenAI · DeepSeek · Kimi · MiMo"]

    subgraph Data["Data and identity"]
        POSTGRES["Postgres<br/>Supabase in production · local in development"]
        AUTH["Supabase Auth<br/>(or dev sign-in locally)"]
    end

    subgraph Deploy["Production: one VM with Docker"]
        CADDY["Caddy<br/>HTTPS · api. · app. · admin."]
        BACKUPS["Daily encrypted pg_dump<br/>Object Storage"]
    end

    ARCA["ARCA<br/>(planned)"]
    MERCADO_PAGO["Mercado Pago<br/>(planned)"]

    WHATSAPP -->|webhook| API
    MESSAGING -->|Cloud API| WHATSAPP
    WORKER["Worker<br/>python -m inmo24x7_api.worker"]
    MAILPIT["SMTP<br/>Mailpit locally"]
    WORKER --> SCHEDULING
    WORKER --> MESSAGING
    WORKER --> CONVERSATION
    NOTIFICATIONS --> MAILPIT
    SCHEDULING --> POSTGRES
    SIMULATOR --> WEB

    WEB --> API
    BACKOFFICE --> API
    CC_WEB -.-> CC_API
    CC_BACKOFFICE -.-> CC_API

    WEB --> UI
    BACKOFFICE --> UI
    CC_WEB -.-> UI
    CC_BACKOFFICE -.-> UI

    WEB --> INMO_CLIENT
    BACKOFFICE --> INMO_CLIENT
    CC_WEB -.-> CC_CLIENT
    CC_BACKOFFICE -.-> CC_CLIENT

    API --> TENANCY
    API --> IDENTITY
    API --> MESSAGING
    API --> SCHEDULING
    LEADS --> NOTIFICATIONS
    API --> CONVERSATION
    API --> PROPERTIES
    API --> LEADS
    LEADS --> CONVERSATION
    LEADS --> PROPERTIES
    PROPERTIES --> POSTGRES
    LEADS --> POSTGRES
    CC_API -.-> TENANCY
    CC_API -.-> IDENTITY
    CC_API -.-> MESSAGING
    CC_API -.-> CONVERSATION

    CONVERSATION --> PORT
    PORT --> LANGGRAPH
    LANGGRAPH --> LLM
    LANGGRAPH --> CHECKPOINTER
    CHECKPOINTER --> POSTGRES
    CONVERSATION --> POSTGRES
    TENANCY --> POSTGRES
    IDENTITY --> AUTH
    CADDY --> API
    CADDY --> WEB
    CADDY --> BACKOFFICE
    BACKUPS --> POSTGRES
    CC_API -.-> ARCA
    CC_API -.-> MERCADO_PAGO

    classDef planned fill:#ffffff,stroke:#8b8b8b,stroke-width:1px,stroke-dasharray: 5 5,color:#666666;
    class CC_WEB,CC_BACKOFFICE,CC_CLIENT,CC_API,ARCA,MERCADO_PAGO planned;
```

The same context layers apply to every bounded context. Dependencies point inward, and the domain has no outward imports.

```mermaid
flowchart LR
    IF["Interface / infrastructure<br/>FastAPI routers · SQLAlchemy · WhatsApp · LangGraph"]
    APP["Application<br/>Use cases"]
    DOMAIN["Domain<br/>Entities · value objects · repository contracts"]

    IF --> APP --> DOMAIN
    DOMAIN -.->|must not import| APP
    DOMAIN -.->|must not import| IF
```

## Requirements

- Docker with Compose.
- [uv](https://docs.astral.sh/uv/).
- Node.js 22.13 or newer. Corepack, included with Node, provides `pnpm`.

## Local development

There are three ways to run it locally. Start with the first one: it needs only Docker.

### a) Zero external services (default)

No Supabase project, no LLM key and no LangSmith: dev sign-in, the fake model and Postgres in
Docker.

```bash
cp .env.example .env
uv run --all-packages python scripts/dev.py --seed
```

`dev.py` installs dependencies, starts Postgres and Mailpit, applies every migration
(`alembic upgrade heads`), seeds the dev accounts (`--seed`, safe to repeat) and starts both
products: each one's API, job worker, panel and backoffice. `--product inmo24x7` or
`--product cuentas-claras` starts only one (the database is shared either way). Press
`Ctrl+C` to stop everything.

| | inmo24x7 | Cuentas Claras |
| --- | --- | --- |
| Panel | http://localhost:5173 | http://localhost:5175 |
| Backoffice | http://localhost:5174 | http://localhost:5176 |
| API (`/docs`, `/health/ready`) | http://localhost:8001 | http://localhost:8002 |

Mailpit (emails sent locally): http://localhost:8025.

Accounts are **invitation-only**: nobody signs up. An admin creates the business in the
backoffice ("Dar de alta un negocio"); that creates the owner's account with a temporary
password (shown once to the admin) and emails an invitation link (Mailpit locally). The owner
comes in either with the temporary password or through the link, and must choose their own
password first (`/cambiar-clave` or `/invitacion`); then the wizard starts. Sign-in is email
and password everywhere; "¿Olvidaste tu clave?" uses Supabase's reset email.

`.env.example` sets `AUTH_MODE=dev` and `VITE_AUTH_MODE=dev`: passwords are checked by the API
(`POST /auth/dev/sign-in`, hashes in the `dev_passwords` table) instead of Supabase, and the
session is the token `dev:<email>`. Seeded accounts (`scripts/seed_dev.py` prints them, with
the invitation links):

| Email | Password | What you get |
| --- | --- | --- |
| `dueno@inmobiliariasur.test` | `local-1234` | Owner of "Inmobiliaria Sur": agent configured, onboarding finished, the 20 properties of `docs/samples/propiedades.csv`, and a fake WhatsApp number (`dev-phone-1`, log sender) for the simulate script. |
| `admin@local.test` | `local-1234` | Platform admin of both backoffices (its own business "Plataforma" in each product). |
| `nuevo@local.test` | `temporal-1234` | Invited to both products ("Nuevo Inmo", "Nuevo Negocio") and never came in: the forced password change, then the wizard from scratch. |
| `invitada@villaurquiza.test` | `temporal-1234` | Invited to "Villa Urquiza Propiedades": try the invitation link (seed output or Mailpit). |
| `dueno@ascensoresdelta.test` | `local-1234` | Cuentas Claras: owner of "Ascensores Delta", onboarding finished, the 40 invoices of `docs/samples/cuentas-claras/facturas.csv` (25 clients) with dates shifted so the sample's reference date is today. |
| `dueno@monitoreosur.test` | `local-1234` | Cuentas Claras: "Monitoreo Sur", suspended. |
| `duena@soporteitnorte.test` | `local-1234` | Cuentas Claras: "Soporte IT Norte", wizard stopped at "Tus facturas", no invoices. |
| `invitado@matafuegosnorte.test` | `temporal-1234` | Cuentas Claras: invited to "Matafuegos Norte", never came in (the invitation link). |

One email is one person (one account, one password), with a separate profile and business in
each product. An email nobody invited signs in to "Tu cuenta no está habilitada".

Dev sign-in is refused when `APP_ENV=production` (the API does not start), and the panels'
production builds fail with `VITE_AUTH_MODE=dev`, so it can never ship. Without `LLM_MODEL`
the agent replies from templates (`FakeLanguageModel`); the flow is the real one.

Local Postgres uses port 5433 to avoid conflicts with other databases.

### b) Local Supabase (Supabase CLI)

To test the real sign-in (Supabase passwords, the reset email) without a cloud project. Install the
[Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started); the
repository already has a `supabase/config.toml` for this (only Supabase Auth is used, the app
keeps its own Postgres). With Docker running:

```bash
supabase start      # first run downloads the images
supabase status     # prints the local URLs and keys
```

Copy the values from `supabase status` into `.env`:

| From `supabase status` | Variable |
| --- | --- |
| API URL (`http://127.0.0.1:54321`) | `SUPABASE_URL` and `VITE_SUPABASE_URL` |
| anon key (or "Publishable key") | `VITE_SUPABASE_ANON_KEY` |
| service_role key (or "Secret key") | `SUPABASE_SERVICE_ROLE_KEY` (the APIs create invited users with it) |
| JWT secret | `SUPABASE_JWT_SECRET` (HS256 tokens) |
| — | or `SUPABASE_JWKS_URL=http://127.0.0.1:54321/auth/v1/.well-known/jwks.json` when the CLI signs with asymmetric keys |

Then set `AUTH_MODE=supabase` and `VITE_AUTH_MODE=supabase` and restart `dev.py`.

- `SUPABASE_URL` must match the token issuer exactly: tokens say `http://127.0.0.1:54321/auth/v1`,
  so `http://localhost:54321` is rejected with 401. Use the same host the CLI prints.
- `supabase/config.toml` already lists the four local apps as redirect URLs and turns sign-up
  off (`enable_signup = false`). If you edit it, run `supabase stop && supabase start`.
- Supabase's own emails ("¿Olvidaste tu clave?") are not sent: open the local mail UI the CLI
  prints (http://127.0.0.1:54324) and click the link there. Invitations go through Mailpit.
- The seed's accounts use dev user ids, so with Supabase start from an empty database and make
  your first admin with `uv run --all-packages python scripts/make_admin.py <email> --create`
  (it prints a temporary password); invite everyone else from the backoffice.

### c) A Supabase cloud project

What production uses. In the project's dashboard: Authentication → Sign In / Providers, turn
off "Allow new users to sign up" (accounts are invitation-only); Authentication → URL
Configuration, add the local apps (`http://localhost:5173/**` to `5176`) as redirect URLs;
Project Settings → API gives the URL, the anon key and the service-role key
(`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) and
the JWT secret or JWKS URL (`SUPABASE_JWT_SECRET` or `SUPABASE_JWKS_URL`). Set both auth modes
to `supabase`, then `make_admin.py <email> --create` for your own user.

### A real model and LangSmith

- Real LLM: set `LLM_MODEL=provider:model` and only that provider's key, for example
  `LLM_MODEL=anthropic:claude-sonnet-5-5` with `ANTHROPIC_API_KEY`. See the environment table.
- LangSmith: `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`; traces go to the agent in
  `LANGSMITH_AGENT_ID` / `LANGSMITH_AGENT_ENVIRONMENT` (`followup-agent-24x7`, `local` in
  `.env.example`), or to the `inmo24x7-dev` project when those are empty. Personal data is
  masked before it is sent.

### Testing WhatsApp locally

**A) No Meta account at all** (log sender, Mailpit). After `dev.py --seed`:

```bash
uv run --all-packages python scripts/simulate_whatsapp.py "Hola, busco un 2 ambientes en Palermo"
uv run --all-packages python scripts/simulate_whatsapp.py "Quiero alquilar"
uv run --all-packages python scripts/simulate_whatsapp.py "Me interesa la primera"
# the slot ids are in Consultas or in the worker log (whatsapp.send); tap one:
uv run --all-packages python scripts/simulate_whatsapp.py --slot slot-202611041000 "mié 4/11 10:00"
uv run --all-packages python scripts/simulate_whatsapp.py "Me llamo Ana"
uv run --all-packages python scripts/simulate_whatsapp.py --audio   # fixed "solo texto" reply
```

The script builds a real Cloud API payload, signs it with `META_APP_SECRET` and posts it to
`/webhooks/whatsapp` from `--from 5491155550188` (default). The worker answers a few seconds
later through the log sender (ids and statuses only in the log). Sign in to the panel as
`dueno@inmobiliariasur.test`: the conversation is in Consultas "por WhatsApp" with Enviado →
Entregado → Leído under each reply, and the new-lead email is in Mailpit
(http://localhost:8025) once the lead is handed off (or 15 minutes after the first message).

**B) The Meta test number, from your phone.**

1. In [Meta for Developers](https://developers.facebook.com/), create an app of type
   *Business* and add the **WhatsApp** product. Meta gives you a test number with a
   `phone_number_id` and a WhatsApp Business Account (WABA) id.
2. In *WhatsApp → API Setup*, add your phone as a test recipient (up to 5) and confirm it.
3. Create a long-lived token: *Business settings → Users → System users*, add a system user,
   assign the app and the WABA, and generate a token with `whatsapp_business_messaging` and
   `whatsapp_business_management`. Do not use the 24-hour temporary token.
4. Expose the API: `cloudflared tunnel --url http://localhost:8001` (or
   `ngrok http 8001`) and copy the https URL.
5. In *WhatsApp → Configuration*: callback URL `https://<tunnel>/webhooks/whatsapp`, verify
   token = your `WHATSAPP_VERIFY_TOKEN`; then subscribe the **messages** field. Set
   `META_APP_SECRET` to the app secret (*App settings → Basic*) and restart `dev.py`.
6. Backoffice → Negocios → open the business → WhatsApp → **Conexión manual y mensaje de
   prueba**: paste the `phone_number_id`, WABA id and token, sender **Cloud API**, Guardar,
   then **Probar conexión**, **Suscribir la app**, and **Enviar mensaje de prueba** to your
   phone (template `hello_world`).
7. Set `WHATSAPP_SENDER=cloud` for new connections, and message the test number from your
   phone. The agent answers on WhatsApp (property messages with links, visit slots as reply
   buttons, hand-off) and the agency's email arrives in Mailpit.

Meta only accepts free-form messages within 24 hours of the person's last message; outside it
the sender refuses with `outside_service_window` and only templates can be sent.

### Testing the inbox: takeover and visit confirmation

`dev.py --seed` already leaves about eight WhatsApp leads for Inmobiliaria Sur (this week and
last, some out of hours, two proposed visits, one confirmed, two asking for a person), created
through the real pipeline, so Inicio and Consultas have data right away.

**A) No Meta account.** Use a new number so the conversation starts fresh:

```bash
alias wa='uv run --all-packages python scripts/simulate_whatsapp.py --from 5491166660001'
wa "Hola" && wa "Quiero alquilar" && wa "Palermo" && wa "Me interesa la primera"
# the slot ids are in the lead's transcript in Consultas (or the worker log); tap one:
wa --slot slot-202611071030 "sáb 7/11 10:30"
wa "Me llamo Ana"
```

1. Consultas → **Para atender**: the lead is there with "Visita propuesta".
2. **Tomar la conversación**: a system event appears; write a reply and **Enviar**. The log
   sender marks it Enviado → Entregado → Leído.
3. `wa "¿Me confirman?"`: the message shows up in the panel within 5 seconds and the agent
   does not answer.
4. **Confirmar visita** (change day and time if you agreed another): the lead receives
   "¡Listo, Ana! Te confirmamos la visita…", the status turns **Visita confirmada**, the
   system event "… confirmó la visita" appears, and the lead leaves **Para atender**.
5. **Devolver al agente** gives the conversation back; the agent reads what the lead told
   the team. Inicio shows the week's KPIs and **Para atender hoy**.

The same works with a simulator conversation (Probar el agente → it shows up in Consultas as
"Prueba"): take it over from Consultas and the team's replies appear in the Probalo chat.

**B) Your phone and the Meta test number.** Same steps after setting up path B above, from
your phone. Within 24 hours of the lead's last message the confirmation is free text; after
that WhatsApp only allows an approved template, so create this one in *WhatsApp Manager →
Message templates* and wait for its approval:

| Field | Value |
| --- | --- |
| Name | `confirmacion_visita` |
| Category | Utility |
| Language | Spanish (ARG), `es_AR` |
| Body | `¡Hola {{1}}! Te confirmamos la visita a {{2}} el {{3}}. Si necesitás cambiar algo, respondé este mensaje.` |
| Examples | `{{1}}` Ana · `{{2}}` Gorriti 4800, Palermo · `{{3}}` sábado 7/11 a las 10:30 |

Then put its name in Backoffice → Negocios → WhatsApp → **Plantilla de confirmación de
visita** and Guardar. Without it, confirming after 24 hours answers
`template_not_configured` and changes nothing. (Meta's test number can only send templates
approved for your app; `hello_world` cannot confirm a visit.)

### Connecting WhatsApp with Embedded Signup (S4)

Customers connect their own number from the panel (wizard step 4 and Configuración →
WhatsApp): **Conectar WhatsApp** opens Meta's Embedded Signup (v4), and the API exchanges the
code, subscribes the app to the customer's WABA, registers the number with a PIN of ours and
reads it. Each step is stored, so **Reintentar configuración** (panel or backoffice) resumes
from the failed one. The manual connection above stays as the fallback and writes the same
connection.

What must exist in Meta first:

1. **Tech Provider** onboarding for your Meta business (business verification approved), and
   the app in **Live** mode.
2. A **Facebook Login for Business** configuration with the **WhatsApp Embedded Signup**
   variation (permissions `whatsapp_business_management` and `whatsapp_business_messaging`).
   Its id is `META_EMBEDDED_SIGNUP_CONFIG_ID` / `VITE_META_EMBEDDED_SIGNUP_CONFIG_ID`; the app
   id is `META_APP_ID` / `VITE_META_APP_ID`.
3. The panel's domain in the app's **Allowed domains** (and *Valid OAuth redirect URIs*) for
   the JavaScript SDK.
4. The webhook (callback `https://<api>/webhooks/whatsapp`) subscribed to the **messages** and
   **account_update** fields. `account_update` tells us when a customer removes the app,
   Meta disables or reinstates an account, or a business verification changes.

The Facebook SDK only runs on HTTPS pages, so locally Embedded Signup needs a tunnel to the
panel (`cloudflared tunnel --url http://localhost:5173`) whose domain is in the allowed
domains. Without `VITE_META_APP_ID` the button is disabled ("La conexión con Meta no está
configurada en este entorno") and you test with the manual fallback: the seed's businesses,
the log sender and `simulate_whatsapp.py`.

**Connection health.** A send or Graph call that fails with an auth error (190, 0, 10,
200–299) puts the connection in error at once: no retry loop, the remaining replies wait as
`waiting_connection`, the panel shows a red banner with the translated message and **Volver
a conectar**, and S9 shows since when messages fail. Reconnecting (Embedded Signup, the
manual form or a successful health check) sends the waiting replies in order; the 24-hour
window still applies. A job reads every Cloud connection every 6 hours (number status,
quality rating, business verification). Try it locally:

```bash
# a webhook as if the customer removed the app (the dev business's WABA is dev-waba-1)
uv run --all-packages python - <<'PY'
import json, sys; sys.path.insert(0, "scripts")
import simulate_whatsapp as s, httpx
body = s.encode({"object": "whatsapp_business_account", "entry": [{"id": "dev-waba-1",
  "changes": [{"field": "account_update", "value": {"event": "PARTNER_APP_UNINSTALLED"}}]}]})
print(httpx.post("http://localhost:8001/webhooks/whatsapp", content=body, headers={
  "Content-Type": "application/json", "X-Hub-Signature-256": s.sign(body, "dev-app-secret")}))
PY
```

Inicio shows the red banner; Backoffice → Inmobiliaria Sur shows the diagnosis, and saving
the manual connection again clears it.

**Suspension** (Backoffice → a business → Suspender, with a reason): the panel answers
`403 tenant_suspended` (except `/me`, which shows "Tu cuenta está suspendida"), WhatsApp
messages are stored but never answered, and no emails or health checks run. Reactivar
resumes everything; nothing is deleted.

### Sample files

`docs/samples/` has `propiedades.csv` (20 valid CABA listings), the same rows as
`propiedades.xlsx`, and `propiedades-con-errores.csv` (5 rows, 3 with the S7 errors: missing
price, invalid link, invalid operation). The seed and the tests use them; import them from
Propiedades to see the report.

`docs/samples/cuentas-claras/` has `facturas.csv` (40 invoices of 25 clients of an elevator
maintenance company), the same rows as `facturas.xlsx`, and `facturas-con-errores.csv` (four
row errors and one warning). Its README explains the reference date.

### Reset the dev database

```bash
uv run --all-packages python scripts/seed_dev.py --reset
```

Drops and recreates the local database (only `localhost` or `127.0.0.1`; it asks first unless
`--yes`), applies every migration and seeds again. It refuses to run with `APP_ENV=production`.

### Manual start

```bash
uv sync --all-packages
corepack pnpm install --frozen-lockfile
docker compose up -d --wait db
uv run alembic upgrade heads
```

Then, in separate terminals:

```bash
uv --directory apps/inmo24x7/api run uvicorn inmo24x7_api.main:app --reload --port 8001
uv --directory apps/inmo24x7/api run python -m inmo24x7_api.worker
corepack pnpm --filter @inmo24x7/web dev
corepack pnpm --filter @inmo24x7/backoffice dev

uv --directory apps/cuentas-claras/api run uvicorn cuentas_claras_api.main:app --reload --port 8002
uv --directory apps/cuentas-claras/api run python -m cuentas_claras_api.worker
corepack pnpm --filter @cuentas-claras/web dev
corepack pnpm --filter @cuentas-claras/backoffice dev
```

One root `alembic.ini` loads every version location against one database and one version
table. Migrations are named branches: `core` (`packages/core/migrations`), `inmo24x7` and
`cuentas_claras` (in each product API). A product revision that needs new core tables declares
`depends_on` that core revision. Always `upgrade heads` (plural): every branch's head.

### Monitoring locally (logs, errors and LLM cost)

- **Logs in Grafana:** `uv run --all-packages python scripts/dev.py --observability` also starts
  Loki, Alloy and Grafana (http://localhost:3000, admin / admin) and copies the API's and the
  worker's output to `.dev-logs/`. Dashboard *inmo24x7 — operación*, environment
  `development`; or Explore with `{environment="development"} | json | tenant_id="<id>"`.
- **Sentry:** set `SENTRY_DSN` (API and worker) and `VITE_SENTRY_DSN` (panels) to a test
  project's DSNs, then Backoffice → Errores → "Enviar errores de prueba". Without DSNs nothing
  is sent and the button says so.
- **LLM cost:** every model call is a row in `llm_usage`; Backoffice → Consumo shows them. The
  fake model costs USD 0 and reports no tokens ("sin datos"). Prices live in
  `packages/platform/src/followup_platform/billing/llm_prices.toml`; after fixing one, recompute
  with `uv run --all-packages python scripts/recompute_llm_costs.py --from 2026-11-01`
  (dry run; add `--apply`).

### Production

Production is one Linux VM with Docker (Oracle Cloud ARM in São Paulo, or any other) behind
Caddy, with Supabase for Postgres and Auth. Everything to run it is in `deploy/`
(`compose.prod.yml`, `Caddyfile`, `deploy.sh` with migrations and rollback, backups and
restore, the VM bootstrap, the Loki + Alloy + Grafana logs stack), and the ordered checklist
is [docs/go-live.md](docs/go-live.md), with Sentry and Grafana under "Monitoring". Before the
first deploy, run the local production rehearsal (`deploy/rehearsal.md`).

## Environment variables

Copy `.env.example` to `.env` to change the defaults. The development script and Vite read the root `.env`. Docker Compose also reads it automatically.

Local defaults apply only while `APP_ENV=development`. With `APP_ENV=production`, startup fails if `DATABASE_URL` or `CORS_ORIGINS` is missing.

Both products read the same variables, except `CORS_ORIGINS` and `PANEL_URL`, which are per
product: inmo24x7 reads them as they are, Cuentas Claras as `CUENTAS_CLARAS_CORS_ORIGINS` and
`CUENTAS_CLARAS_PANEL_URL` (table below). Its panels read `VITE_CUENTAS_CLARAS_API_URL`.

| Variable | Local default | Used by | Description |
| --- | --- | --- | --- |
| `APP_ENV` | `development` | API | `development` or `production`. |
| `POSTGRES_USER` | `followup` | Docker Compose | Initial local Postgres user. |
| `POSTGRES_PASSWORD` | `followup` | Docker Compose | Initial local Postgres password. |
| `POSTGRES_DB` | `followup` | Docker Compose | Local development database name. |
| `DATABASE_URL` | `postgresql+psycopg://followup:followup@localhost:5433/followup` | API, Alembic | Postgres connection. Required in production. |
| `TEST_DATABASE_URL` | `postgresql+psycopg://followup:followup@localhost:5433/followup_test` | API tests | Dedicated test database. Tests create it when necessary and never modify the development database. |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:5174` | API | Allowed origins, separated by commas. Required in production. |
| `VITE_API_URL` | `http://localhost:8001` | Web, backoffice | Public API URL. It is embedded in the panel builds. |
| `AUTH_MODE` | `dev` (`.env.example`); unset: `dev` in development, `supabase` in production | API | `supabase` verifies Supabase JWTs; `dev` accepts only `dev:<email>` tokens (local development). `AUTH_MODE=dev` with `APP_ENV=production` stops the API at startup. |
| `VITE_AUTH_MODE` | `dev` (`.env.example`); unset: `supabase` | Web, backoffice | `dev` checks passwords with the API (`/auth/dev/sign-in`) instead of Supabase. A production build (`vite build`) fails with `dev`. |
| `SUPABASE_URL` | *(empty)* | API | Supabase project URL. Required in production; tokens must be issued by `{SUPABASE_URL}/auth/v1`. |
| `SUPABASE_JWT_SECRET` | *(empty)* | API | Supabase JWT secret (HS256). `AUTH_MODE=supabase` requires this or `SUPABASE_JWKS_URL`. |
| `SUPABASE_JWKS_URL` | *(empty)* | API | JWKS URL for tokens signed with ES256 or RS256. `AUTH_MODE=supabase` requires this or `SUPABASE_JWT_SECRET`. |
| `VITE_SUPABASE_URL` | *(empty)* | Web, backoffice | Supabase URL for the auth client in the panels (`VITE_AUTH_MODE=supabase`). Empty counts as unset. |
| `VITE_SUPABASE_ANON_KEY` | *(empty)* | Web, backoffice | Supabase anon key for the auth client in the panels. Empty counts as unset. |
| `LLM_MODEL` | *(empty)* | API | Agent model as `provider:model`, with provider `anthropic`, `openai`, `deepseek`, `kimi` or `mimo` (for example `anthropic:claude-sonnet-5-5`). Empty in development uses a template-based fake model and logs a warning. Required in production. |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `MOONSHOT_API_KEY`, `MIMO_API_KEY` | *(empty)* | API | API key of the provider named in `LLM_MODEL` (Kimi uses `MOONSHOT_API_KEY`). Only that one is read, and it is required whenever `LLM_MODEL` is set. |
| `LLM_BASE_URL` | *(empty)* | API | Optional endpoint override, e.g. Moonshot's China endpoint or MiMo's Token Plan URL. Kimi and MiMo default to their global OpenAI-compatible URLs. |
| `LLM_TIMEOUT_SECONDS` | `20` | API | Timeout per model call. The adapter retries once; then the simulator returns `503 agent_unavailable`. |
| `SIMULATOR_DAILY_LIMIT` | `300` | API | Simulator messages per business per day (in the business's timezone). Over it the API returns `429 simulator_limit_reached`. |
| `LANGSMITH_TRACING` | `false` | API | `true` sends a trace of every agent turn to LangSmith. Optional in every environment; tests and CI force it off. |
| `LANGSMITH_API_KEY` | *(empty)* | API | LangSmith key. Without it tracing stays off (with a warning), it never fails startup. |
| `LANGSMITH_AGENT_ID`, `LANGSMITH_AGENT_ENVIRONMENT` | `followup-agent-24x7`, `local` (`.env.example`) | API | LangSmith agent the turns are sent to. Set both: the id is a lowercase DNS label, the environment is `local`, `development`, `staging` or `production`. Only one of them, or an invalid value, leaves tracing off with a warning. |
| `LANGSMITH_PROJECT` | `inmo24x7-dev` / `inmo24x7-prod` | API | Project for the traces when no agent is set; the default follows `APP_ENV`. Ignored when the agent variables are set. |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com` | API | Change it only for the EU region or a self-hosted LangSmith. |
| `LANGSMITH_TRACING_SAMPLING_RATE` | *(all turns)* | API | Fraction of turns traced, from 0 to 1. |
| `LANGSMITH_REDACT_PII` | `true` | API | Masks emails, Argentine phone numbers and DNIs in every traced input and output before it is sent. |
| `LANGSMITH_UI_URL` | *(empty)* | API | The project's page in the LangSmith UI (`…/o/<org>/projects/p/<project-id>`). When set, backoffice simulator messages get a "Ver traza" link. |
| `LANGSMITH_HIDE_INPUTS`, `LANGSMITH_HIDE_OUTPUTS` | *(unset)* | API | Read by the LangSmith client: `true` drops inputs or outputs from traces entirely, keeping only names, timing and metadata. |
| `WHATSAPP_SENDER` | `log` (`.env.example`); unset: `log` in development, `cloud` in production | API, worker | Default sender for new connections: `cloud` (Meta's Cloud API) or `log` (nothing leaves the machine; statuses are simulated). Production requires `cloud`. Each connection stores its own. |
| `META_APP_SECRET` | `dev-app-secret` | API | Verifies `X-Hub-Signature-256` on every webhook. Required in production (the dev value is refused). |
| `WHATSAPP_VERIFY_TOKEN` | `dev-verify-token` | API | The token you type in Meta's webhook configuration. Required in production. |
| `META_GRAPH_BASE_URL`, `META_GRAPH_API_VERSION` | `https://graph.facebook.com`, `v26.0` | API, worker | Graph API endpoint and version. |
| `WHATSAPP_DEFAULT_TEMPLATE`, `WHATSAPP_DEFAULT_TEMPLATE_LANGUAGE` | `hello_world`, `en_US` | API | Template for new connections (messages outside the 24-hour window, "Enviar mensaje de prueba"). |
| `TOKEN_ENCRYPTION_KEY` | a dev key in `.env.example` | API, worker | Base64 of 32 bytes; encrypts WhatsApp access tokens (AES-GCM). Required in production, where the dev key is refused. Generate with `python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"`. |
| `INBOUND_DEBOUNCE_SECONDS` | `3` | Worker | How long the worker waits for more messages before answering a burst. |
| `WORKER_CONCURRENCY` | `4` | Worker | Jobs run at the same time per worker process. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS` | `localhost`, `1025`, —, —, `false` | Worker | Where new-lead emails go (Mailpit locally). `SMTP_HOST` is required in production; STARTTLS defaults to on there. |
| `EMAIL_FROM` | `inmo24x7 <avisos@inmo24x7.local>` | Worker | Sender of the new-lead emails. Required in production. |
| `PANEL_URL` | `http://localhost:5173` | API, worker | The panel's public URL, for links in emails ("Ver la consulta") and sample property links on WhatsApp. Required in production. |
| `META_APP_ID`, `META_EMBEDDED_SIGNUP_CONFIG_ID` | *(empty)* | API | Embedded Signup: the app id (public) and the Facebook Login for Business configuration id. The code exchange also uses `META_APP_SECRET`. Required in production; empty locally (manual fallback). |
| `VITE_META_APP_ID`, `VITE_META_EMBEDDED_SIGNUP_CONFIG_ID`, `VITE_META_GRAPH_API_VERSION` | *(empty)*, *(empty)*, `v26.0` | Web | The same ids for the Facebook SDK in the panel (build time). Without them "Conectar WhatsApp" is disabled. |
| `SUPPORT_EMAIL` | `soporte@inmo24x7.local` | API | Shown on the suspended-account screen. Required in production. |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | `5`, `1` | API, worker | Database connections per process. Supabase's session pooler gives each its own server connection, so keep the total under the plan's pool (docs/go-live.md has the math). The worker needs at least `WORKER_CONCURRENCY + 1`. A `DATABASE_URL` on port 6543 (the transaction pooler) is refused. |
| `SUPABASE_SERVICE_ROLE_KEY` | *(empty)* | API | The service-role (secret) key: the APIs create invited users and set passwords through Supabase Auth's admin API. Server-side only, never in a panel build. Required in production. |
| `SUPABASE_SERVER_URL` | *(empty: `SUPABASE_URL`)* | API | Where the API reaches Supabase Auth when that differs from the token issuer. Only the local rehearsal needs it. |
| `REHEARSAL` | `false` | API, worker | Only for the local production rehearsal (`deploy/rehearsal.md`): with `APP_ENV=production`, allows the fake model and the log sender. Never set on a server. |
| `SENTRY_DSN` | *(empty: off)* | API, worker | Sends errors to Sentry (unhandled exceptions, dead jobs, WhatsApp connections in error, LLM failures after the retry). No bodies, query strings, cookies or personal data: see ARCHITECTURE.md, "Observability". |
| `SENTRY_TRACES_SAMPLE_RATE` | `0` | API, worker | Fraction of requests traced for performance (0 to 1). Off by default. |
| `SENTRY_API_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECTS`, `SENTRY_API_URL` | *(empty)*, *(empty)*, *(empty)*, `https://sentry.io` | API | The backoffice's Errores page reads open issues with a read-only token. `SENTRY_PROJECTS` is `api=<slug>,panel=<slug>,backoffice=<slug>`; `SENTRY_API_URL` is `https://de.sentry.io` for EU organizations. Without them the page says Sentry is not configured. |
| `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT` | *(empty)*, `production` | Web, backoffice | The panel's own Sentry DSN (build time; CI uses `SENTRY_DSN_PANEL` / `SENTRY_DSN_BACKOFFICE`). Empty: off. The release is the commit (`GIT_COMMIT`). |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT_PANEL`, `SENTRY_PROJECT_BACKOFFICE` | *(CI only)* | CI | Uploads the panels' source maps to Sentry and deletes them from the image. Without the secret no source maps are built. |
| `SENTRY_INGEST_HOST` | *(empty)* | Caddy | The panels' Sentry host, allowed in the CSP's `connect-src` (`https://o<id>.ingest.us.sentry.io`). |
| `GRAFANA_URL`, `LOKI_DATASOURCE` | *(empty)*, `loki` | API | The backoffice's "Ver logs" and "Buscar por código de referencia" links into Grafana Explore. Empty: the links are hidden. |
| `COMPOSE_PROFILES`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_DOMAIN`, `GRAFANA_ALLOWED_IPS`, `LOKI_RETENTION_DAYS`, `ALERTS_EMAIL_FROM` | *(production only)* | Loki, Alloy, Grafana | The self-hosted logs stack on the VM (`deploy/observability.md`). |
| `LLM_MONTHLY_COST_ALERT_USD` | *(empty: off)* | Worker | A daily job emails `SUPPORT_EMAIL` once per business and month when its LLM cost reaches this many USD. |
| `CUENTAS_CLARAS_CORS_ORIGINS` | `http://localhost:5175,http://localhost:5176` | Cuentas Claras API | Its allowed origins. Required in production. |
| `CUENTAS_CLARAS_PANEL_URL` | `http://localhost:5175` | Cuentas Claras API, worker | Its panel's public URL. Required in production. |
| `VITE_CUENTAS_CLARAS_API_URL` | `http://localhost:8002` | Cuentas Claras web, backoffice | Its API's public URL, embedded in the builds (its own name: `VITE_API_URL` is inmo24x7's). |
| `CUENTAS_CLARAS_SENTRY_DSN`, `CC_*_DOMAIN`, `CC_*_DB_POOL_SIZE` | *(production only)* | Compose, Caddy | Cuentas Claras on the VM (`deploy/.env.production.example`), off until its profile is on. |
| `VITE_PANEL_URL` | `http://localhost:5173` | Backoffice | Panel origin, used to open sample property links from the backoffice simulator. Optional Docker build argument. |
| `APP_VERSION` | `0.1.0` | API, Docker | Version returned by readiness. Passed as a Docker build argument. |
| `GIT_COMMIT` | `unknown` | API, Docker | Commit returned by readiness. Passed as a Docker build argument. |
| `BUILD_DATE` | `unknown` | API, Docker | Build date returned by readiness. Passed as a Docker build argument. |

The API reads the `SUPABASE_*`, LLM and `LANGSMITH_*` variables only at runtime; they are never Docker build arguments, so they cannot end up in an image layer. Only the public `VITE_SUPABASE_*` values are embedded in the panel builds. The same goes for `META_*`, `WHATSAPP_*`, `TOKEN_ENCRYPTION_KEY` and `SMTP_*`. The repository contains no real secrets: the values in `.env.example` are development-only and production refuses them.

Only the development script loads `.env` into API processes. When using the manual commands, export the variables in your shell.

## Tests and lint

The API integration tests use a real Postgres database and build its schema by running the Alembic migrations. Locally, make sure the compose database is running:

```bash
docker compose up -d --wait db
uv run --all-packages pytest
```

Fast unit tests use in-memory repositories. CI runs the API tests against a Postgres service container. The seed tests (`test_seed_dev.py`) run the seed twice against the test database, never the development one.

```bash
uv run pyright
uv run ruff check .
uv run ruff format --check .
uv run --all-packages python scripts/generate_types.py

corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
```

The generated OpenAPI schemas live in `packages/api-client-inmo24x7/src/schema.ts` and `packages/api-client-cuentas-claras/src/schema.ts`. CI regenerates both and fails when a committed file is out of date.

## API

```bash
curl http://localhost:8001/health
curl http://localhost:8001/health/ready
curl "http://localhost:8001/tenants?page=1&limit=10"
curl -X POST http://localhost:8001/tenants \
  -H "Content-Type: application/json" \
  -d '{"name":"Sun Realty"}'
```

`GET /tenants` returns:

```json
{
  "items": [],
  "page": 1,
  "limit": 10,
  "total": 0,
  "total_pages": 0
}
```

All routes below need an access token (Supabase, or `dev:<email>` with `AUTH_MODE=dev`) and are scoped to the caller's business. Writes need the owner or manager role (otherwise `403 {"code": "forbidden"}`).

| Route | Purpose |
| --- | --- |
| `POST /me/sign-up` | No body. Joins the business an admin created for the signed-in email (owner profile); idempotent. `403 not_invited` when nobody invited this email to this product. |
| `GET /account`, `POST /account/password` `{password}` | The account (`must_change_password`) and the password change. Until a temporary password is changed every other route answers `403 password_change_required`. `422 password_too_short`, `password_too_long`, `password_is_email`. |
| `GET /invitations/{token}`, `POST /invitations/accept` `{token, password}` | No access token: the emailed link (`status valid\|expired\|used`, `needs_password`) and choosing the password through it. `404 invitation_not_found`, `409 invitation_used`, `410 invitation_expired`. Links last 7 days; a resend replaces the previous one. |
| `POST /auth/dev/sign-in` `{email, password}` | `AUTH_MODE=dev` only (404 otherwise): the `dev:<email>` token for the right password, `401 invalid_credentials` otherwise. |
| `GET /onboarding`, `POST /onboarding/advance` | Wizard progress and setup checklist. |
| `GET /agent-setup`, `PUT /agent-setup` | Agent configuration plus team hours and notification emails, saved together. |
| `GET /agent-setup/versions` | Latest 20 agent configuration versions. |
| `GET /tenant/settings`, `PUT /tenant/settings` | Business name, type, hours and notification emails. |
| `GET /simulator` | The caller's current simulator thread: transcript, "Lo que el agente ya sabe" rows, sample-properties and outdated-config flags. Creates nothing. Any role. |
| `POST /simulator/messages` | Send `{text}` (1–1000 characters); returns the agent's new messages and the state panel. `503 agent_unavailable` if the model fails (nothing is stored), `429 simulator_limit_reached` over the daily limit. |
| `POST /simulator/reset` | Reiniciar: start a new thread pinned to the current agent configuration. |
| `GET /admin/tenants/{tenant_id}/simulator`, `.../messages`, `.../reset` | Platform admins only: the same simulator against any business, in the admin's own thread. |
| `GET /properties?search=&operation=&status=&page=` | S7 list, 20 per page, with inquiries per property. Search covers address and zone, without accents or case. |
| `POST /properties`, `PATCH /properties/{id}` | Manual create and edit. `422 property_invalid`, `409 property_link_taken`, `404 property_not_found`. |
| `POST /properties/{id}/publish`, `POST /properties/{id}/pause` | Publish or pause (there is no delete). |
| `POST /properties/import` | Multipart `file` (CSV or XLSX, up to 5 MB and 2,000 rows): report with `imported`, `total`, `failed` and the row errors. `413 import_too_large`, `422 import_file_invalid`. |
| `GET /properties/import/{id}/errors.csv`, `GET /properties/import-template.csv` | The failed rows plus an `error` column, and the template with the Spanish headers. |
| `GET /leads?tab=attention\|visits\|all&q=&include_test=&page=` | The inbox: 25 per page, with `counts` per tab. `attention` = needs the team (most urgent first), `visits` = proposed or confirmed visit (by visit time), `all` = by last activity. `q` matches name, zone/answers or a phone in any format, accent-insensitive. Simulator leads only with `include_test=true`. |
| `GET /leads/export.csv?tab=&q=&include_test=` | The same leads as CSV (UTF-8 with BOM, `;`), one column per configured question, at most 5,000 rows. |
| `POST /leads/{id}/takeover`, `POST /leads/{id}/release` | Take the conversation from the agent (also from a teammate) or give it back. Owner, manager, agent; `403 forbidden` for viewers. |
| `POST /leads/{id}/messages` `{text}` | A team reply, sent on WhatsApp by the send job. `409 conversation_not_taken`, `409 outside_service_window`. |
| `POST /leads/{id}/visits/{visit_id}/confirm` `{starts_at?}` | Confirms (optionally at another future time) and tells the lead: text, or the visit template after 24 hours. `409 template_not_configured`, `409 visit_cancelled`, `422 visit_time_in_past`. |
| `POST /leads/{id}/visits/{visit_id}/cancel` `{message?}` | Cancels the visit; the lead goes back to "Pidió hablar con alguien". |
| `GET /dashboard` | Inicio: this week's KPIs (received and out of hours, qualified, visits, average response) and "Para atender hoy". Real leads only. |
| `GET /whatsapp` | The business's WhatsApp status for the panel (badge, S4 card, error banner): number, quality, business verification, `error {code, title, message, action}` in Spanish, `failing_since`, and the signup step when it stopped halfway. Any role. |
| `POST /whatsapp/embedded-signup` `{code, waba_id, phone_number_id, business_id?}` | Embedded Signup: exchange, subscribe, register, read, connect. Owner or manager. `409 whatsapp_phone_number_taken`, `502 whatsapp_signup_failed {step, meta_code, error}` (progress is kept). |
| `POST /whatsapp/embedded-signup/retry` | Resumes from the failed step with the stored token. `409 whatsapp_signup_restart` when the code was never exchanged. |
| `POST /whatsapp/embedded-signup/abandoned` `{event, current_step?, error_code?}` | Records a CANCEL / ERROR / FINISH_ONLY_WABA from Meta's popup; returns Meta's code in Spanish. |
| `GET /webhooks/whatsapp`, `POST /webhooks/whatsapp` | Meta's webhook: verification, and messages/statuses (signed with `X-Hub-Signature-256`; no access token). |
| `GET/PUT /admin/tenants/{id}/whatsapp`, `POST .../test`, `.../subscribe`, `.../test-message`, `.../disconnect` | Platform admins: manual connection. The token is never returned. `whatsapp_api_error` includes `meta_code`. |
| `POST /admin/tenants/{id}/whatsapp/retry-signup`, `.../reconnect-link` | "Reintentar configuración" and "Enviarle link para reconectar" (emails the owners a link to Configuración → WhatsApp). |
| `GET /admin/tenants?filter=all\|needs_help\|trial&q=&page=` | S8: businesses with plan, onboarding "N de 5", WhatsApp badge, inquiries in 7 days, and the four KPIs. |
| `POST /admin/tenants` `{business_name, owner_email}` | "Dar de alta un negocio": the business, the owner's account and the invitation email. Returns the detail plus `temporary_password` (once; null when the person already had an account). `409 owner_email_taken`. |
| `POST /admin/tenants/{id}/invitation`, `POST /admin/tenants/{id}/temporary-password` | While the owner has not come in: resend the invitation (a new link) or a new temporary password (shown once). `409 owner_already_joined`. |
| `GET /admin/tenants/{id}`, `POST .../suspend {reason}`, `.../reactivate` | S9: WhatsApp diagnosis (WABA masked), activity (audit log), onboarding, plan usage, users; suspension. |
| `GET /admin/system`, `GET /admin/plans` | Salud del sistema (jobs, webhooks, signature rejections, failed sends by Meta code, version, database, monitoring links) and Planes. |
| `GET /admin/errors?project=all\|api\|panel\|backoffice&period=24h\|7d\|14d&tenant_id=` | Errores: open Sentry issues (cached one minute). `{configured: false}` without the Sentry settings, `{available: false}` when Sentry fails; never a 500. |
| `POST /admin/errors/test` | Fails on purpose (500, `SentryTestError`) to check Sentry end to end. |
| `GET /admin/usage?month=YYYY-MM`, `GET /admin/usage/{tenant_id}?month=`, `GET /admin/usage/export.csv?month=` | Consumo (UTC months): LLM cost, tokens, conversations, cost per conversation, simulator share and WhatsApp templates per business; one business's daily series and split by task and model; the table as CSV. |
| `GET /leads/{id}` | The same plus answers (the configured questions, in order), status history, visits, the transcript (system events, team authors, delivery), who controls the conversation and the WhatsApp 24-hour window. `404 lead_not_found`. |

### Cuentas Claras API (port 8002)

The same `/me`, sign-up, `/account`, `/invitations`, `/onboarding`, `/tenant/settings` and
`/health` routes (shared from `followup_platform`), scoped to Cuentas Claras's businesses,
plus:

| Route | Purpose |
| --- | --- |
| `GET /invoices?tab=pending\|overdue\|promised\|paid_this_month&q=&page=` | Facturas: 25 per page with `counts` per tab. Each item has the client, the number (`B 0003-00001245`), amount and currency, due date, display status `{kind, label, days_overdue}` in the business's timezone, and `next_action` (null until Day 9). `q` matches the client, a CUIT, or a number as `1245`, `0003-00001245` or `B 3-1245`. |
| `POST /invoices`, `GET/PATCH /invoices/{id}` | Create, detail (client and payment), edit. `422 invoice_invalid`, `409 invoice_number_taken`, `404 invoice_not_found`. |
| `POST /invoices/{id}/mark-paid` `{paid_at, paid_via, reference?}`, `POST /invoices/{id}/cancel` `{reason}` | "Marcar como pagada" and "Anular" (only open invoices: `409 invoice_already_paid`). |
| `POST /invoices/import` | Multipart `file` (CSV or XLSX, 5 MB, 5,000 rows): `{created, updated, skipped, failed, errors[], warnings[]}`. Re-importing updates open invoices and never reopens a paid one. |
| `GET /invoices/import/{id}/errors.csv`, `GET /invoices/import-template.csv` | The failed rows with an `error` column; the template. |
| `GET /summary` | Inicio's "Total a cobrar" and "Vencido" (ARS, and USD apart). |
| `GET /clients?q=&missing_whatsapp=&page=`, `POST /clients`, `GET/PATCH /clients/{id}` | Clientes with open invoices and amount owed per currency; the detail includes its invoices. `422 cuit_invalid`, `409 cuit_taken`, `422 client_invalid`. |
| `GET /admin/tenants?q=&page=`, `POST /admin/tenants`, `GET /admin/tenants/{id}`, `POST .../suspend`, `.../reactivate`, `.../invitation`, `.../temporary-password` | Platform admins: Cuentas Claras's businesses only, "Dar de alta un negocio" and the invitation actions as in inmo24x7. |

Errors return stable codes instead of user-facing text:

```json
{"code": "tenant_slug_taken"}
```

The frontends map those codes to Spanish messages. Every response includes an `X-Request-ID` header, and logs are emitted as JSON.

## Structure

```text
apps/inmo24x7/api                  FastAPI API and product migrations
apps/inmo24x7/web                  customer panel
apps/inmo24x7/backoffice           internal administration
apps/cuentas-claras/api            Cuentas Claras API (clients, invoices, import) and its migrations
apps/cuentas-claras/web            Cuentas Claras panel
apps/cuentas-claras/backoffice     Cuentas Claras administration
packages/core                      shared domain, application, adapters, core migrations
packages/platform                  shared API plumbing (followup_platform): settings, auth,
                                   errors, logging, Sentry, worker loop, shared routers
packages/ui                        shared React components (@followup/ui)
packages/app-shell                 shared panel pieces (@followup/app-shell): auth, sign-in,
                                   guards, wizard frame, checklist, settings fields, API client
packages/api-client-inmo24x7       generated OpenAPI types and typed client
packages/api-client-cuentas-claras generated OpenAPI types for Cuentas Claras
packages/observability             Sentry setup, PII scrubbing and error boundary for the panels
alembic.ini                        single migration configuration
migrations                         root Alembic environment
scripts                            local startup, dev seed, make_admin and type generation
docs/samples                       sample property and invoice files (CSV, XLSX, CSV with errors)
supabase                           local Supabase CLI configuration (auth only)
```

## Images

On every push to `master`, after the tests, CI's `release-gate` job checks each product's
repository variables, and for each product that has them builds amd64 + arm64 images for its
API, web and backoffice and pushes them to GitHub Container Registry as `sha-<commit>` (and
`latest`). A product without them is skipped with a notice, never a failure. The panel
builds embed only public values (the API URL, the Supabase URL and anon key, and for
inmo24x7 the Meta app and Embedded Signup ids). Secrets are runtime environment only. Deploying is
`deploy/deploy.sh <commit>` on the VM: see [docs/go-live.md](docs/go-live.md).

## License

TODO: choose a license before distributing this project.
