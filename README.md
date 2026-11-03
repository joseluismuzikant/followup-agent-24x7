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

Dashed components and edges are planned.

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
        POSTGRES["Postgres<br/>local development"]
        SUPABASE["Postgres on Supabase<br/>(planned)"]
        AUTH["Supabase Auth<br/>(or dev sign-in locally)"]
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
    POSTGRES -.-> SUPABASE
    IDENTITY --> AUTH
    AUTH -.-> SUPABASE
    CC_API -.-> ARCA
    CC_API -.-> MERCADO_PAGO

    classDef planned fill:#ffffff,stroke:#8b8b8b,stroke-width:1px,stroke-dasharray: 5 5,color:#666666;
    class CC_WEB,CC_BACKOFFICE,CC_CLIENT,CC_API,SUPABASE,ARCA,MERCADO_PAGO planned;
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

`dev.py` installs dependencies, starts Postgres and Mailpit, applies migrations, seeds the dev
accounts (`--seed`, safe to repeat) and starts the API, the job worker and both panels. Press
`Ctrl+C` to stop everything.

- Panel: http://localhost:5173
- Backoffice: http://localhost:5174
- API: http://localhost:8001 (documentation at `/docs`, readiness at `/health/ready`)
- Mailpit (emails sent locally): http://localhost:8025

`.env.example` sets `AUTH_MODE=dev` and `VITE_AUTH_MODE=dev`. The sign-in screens then show a
**Modo desarrollo** box: type an email and press **Entrar**, no password. The session is the
token `dev:<email>`, and the API maps each email to a fixed user id. Seeded accounts:

| Email | What you get |
| --- | --- |
| `dueno@inmobiliariasur.test` | Owner of "Inmobiliaria Sur": agent configured, onboarding finished, the 20 properties of `docs/samples/propiedades.csv`, and a fake WhatsApp number (`dev-phone-1`, log sender) for the simulate script. |
| `admin@local.test` | Platform admin (its own business "Plataforma"): use it in the backoffice. |
| `nuevo@local.test` | No account yet: try sign-up and the wizard from scratch. Any other email works the same way. |

Dev sign-in is refused when `APP_ENV=production` (the API does not start), and the panels'
production builds fail with `VITE_AUTH_MODE=dev`, so it can never ship. Without `LLM_MODEL`
the agent replies from templates (`FakeLanguageModel`); the flow is the real one.

Local Postgres uses port 5433 to avoid conflicts with other databases.

### b) Local Supabase (Supabase CLI)

To test the real sign-in (magic link, optionally Google) without a cloud project. Install the
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
| JWT secret | `SUPABASE_JWT_SECRET` (HS256 tokens) |
| — | or `SUPABASE_JWKS_URL=http://127.0.0.1:54321/auth/v1/.well-known/jwks.json` when the CLI signs with asymmetric keys |

Then set `AUTH_MODE=supabase` and `VITE_AUTH_MODE=supabase` and restart `dev.py`.

- `SUPABASE_URL` must match the token issuer exactly: tokens say `http://127.0.0.1:54321/auth/v1`,
  so `http://localhost:54321` is rejected with 401. Use the same host the CLI prints.
- `supabase/config.toml` already lists `http://localhost:5173` and `http://localhost:5174` as
  redirect URLs. If you edit it, run `supabase stop && supabase start`.
- Magic-link emails are not sent: open the local mail UI the CLI prints
  (http://127.0.0.1:54324) and click the link there.
- Google sign-in is optional and needs a Google OAuth client: set
  `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID` and `SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET`, and turn
  on `[auth.external.google]` in `supabase/config.toml`.
- The seed's accounts use dev user ids, so with Supabase sign up through the panel instead and
  grant the backoffice with `uv run --all-packages python scripts/make_admin.py <email>`.

### c) A Supabase cloud project

What production uses. In the project's dashboard: Authentication → URL Configuration, add
`http://localhost:5173` and `http://localhost:5174` as redirect URLs; Project Settings → API
gives the URL and anon key (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `SUPABASE_URL`) and
the JWT secret or JWKS URL (`SUPABASE_JWT_SECRET` or `SUPABASE_JWKS_URL`). Set both auth modes
to `supabase`, then `make_admin.py <email>` for your own user once you signed up.

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
6. Backoffice → Negocios → **WhatsApp** on the business row: paste the `phone_number_id`,
   WABA id and token, sender **Cloud API**, Guardar, then **Probar conexión**, **Suscribir la
   app**, and **Enviar mensaje de prueba** to your phone (template `hello_world`).
7. Set `WHATSAPP_SENDER=cloud` for new connections, and message the test number from your
   phone. The agent answers on WhatsApp (property messages with links, visit slots as reply
   buttons, hand-off) and the agency's email arrives in Mailpit.

Meta only accepts free-form messages within 24 hours of the person's last message; outside it
the sender refuses with `outside_service_window` and only templates can be sent.

### Sample files

`docs/samples/` has `propiedades.csv` (20 valid CABA listings), the same rows as
`propiedades.xlsx`, and `propiedades-con-errores.csv` (5 rows, 3 with the S7 errors: missing
price, invalid link, invalid operation). The seed and the tests use them; import them from
Propiedades to see the report.

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
uv run alembic upgrade head
```

Then, in separate terminals:

```bash
uv --directory apps/inmo24x7/api run uvicorn inmo24x7_api.main:app --reload --port 8001
corepack pnpm --filter @inmo24x7/web dev
corepack pnpm --filter @inmo24x7/backoffice dev
```

One root `alembic.ini` loads every version location against one database and one version table. Core revisions live in `packages/core/migrations`; product revisions live in each product API. Product revision chains start from the current core head.

### Production migrations

Run migrations once as a one-off container from the API image before starting the new API version:

```bash
docker run --rm \
  -e APP_ENV=production \
  -e DATABASE_URL=postgresql+psycopg://user:password@host:5432/database \
  -e CORS_ORIGINS=https://app.example.com \
  ghcr.io/owner/repository/inmo24x7-api:sha-<commit> \
  alembic upgrade head
```

The API image contains the root Alembic configuration and runs from `/app`. Start the new API only after the migration exits successfully.

The same image runs the job worker (WhatsApp processing and sending, new-lead emails) with
another command; run at least one next to the API, with the same environment:

```bash
docker run -d --env-file production.env ghcr.io/owner/repository/inmo24x7-api:sha-<commit> \
  python -m inmo24x7_api.worker
```

## Environment variables

Copy `.env.example` to `.env` to change the defaults. The development script and Vite read the root `.env`. Docker Compose also reads it automatically.

Local defaults apply only while `APP_ENV=development`. With `APP_ENV=production`, startup fails if `DATABASE_URL` or `CORS_ORIGINS` is missing.

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
| `VITE_AUTH_MODE` | `dev` (`.env.example`); unset: `supabase` | Web, backoffice | `dev` shows the "Modo desarrollo" sign-in instead of Google and the magic link. A production build (`vite build`) fails with `dev`. |
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

The generated OpenAPI schema lives in `packages/api-client-inmo24x7/src/schema.ts`. CI regenerates it and fails when the committed file is out of date.

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
| `POST /me/sign-up` | Create the business, owner profile, default settings and onboarding record. Body: `{business_name, business_type}`. |
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
| `GET /leads?status=&include_test=&page=` | Leads, newest activity first: name or contact, what they look for, status, test flag. Simulator leads only with `include_test=true`. |
| `GET /whatsapp` | The business's WhatsApp status for the panel (badge, wizard step 4). Any role. |
| `GET /webhooks/whatsapp`, `POST /webhooks/whatsapp` | Meta's webhook: verification, and messages/statuses (signed with `X-Hub-Signature-256`; no access token). |
| `GET/PUT /admin/tenants/{id}/whatsapp`, `POST .../test`, `.../subscribe`, `.../test-message`, `.../disconnect` | Platform admins: manual connection. The token is never returned. `whatsapp_api_error` includes `meta_code`. |
| `GET /leads/{id}` | The same plus answers, status history, visits and the transcript (with system events). `404 lead_not_found`. |

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
apps/cuentas-claras                second product scope
packages/core                      shared domain, application, adapters, core migrations
packages/ui                        shared React components (@followup/ui)
packages/api-client-inmo24x7       generated OpenAPI types and typed client
alembic.ini                        single migration configuration
migrations                         root Alembic environment
scripts                            local startup, dev seed, make_admin and type generation
docs/samples                       sample property files (CSV, XLSX, CSV with errors)
supabase                           local Supabase CLI configuration (auth only)
```

## Images

On every push to the repository's default branch, after tests pass, CI builds and pushes amd64 + arm64 images for the API, web, and backoffice to GitHub Container Registry. Images use `latest` and `sha-<commit>` tags. The API receives `APP_VERSION`, `GIT_COMMIT`, and `BUILD_DATE`; the panels receive `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` (public by design), and `VITE_API_URL` from the `INMO24X7_API_URL` repository variable (or the `INMO24X7_API_URL` secret). If neither is set, CI falls back to `http://localhost:8001`; set it to the production API URL before deploying.

Run the API image with `APP_ENV=production`, `DATABASE_URL`, `CORS_ORIGINS`, `SUPABASE_URL`, and `SUPABASE_JWT_SECRET` (or `SUPABASE_JWKS_URL`) set at runtime (`docker run -e` or an env file). Never pass Supabase secrets as build arguments.

Local multi-architecture build:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  --build-arg APP_VERSION=0.1.0 \
  --build-arg GIT_COMMIT="$(git rev-parse HEAD)" \
  --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -f apps/inmo24x7/api/Dockerfile \
  -t my-registry/inmo24x7-api:latest --push .
```

Use the same pattern with the `web` and `backoffice` Dockerfiles. Both require `--build-arg VITE_API_URL=https://api.example.com`; the build fails without it.

## License

TODO: choose a license before distributing this project.
