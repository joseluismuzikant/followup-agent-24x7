# followup-agent-24x7

## What this is

A platform of WhatsApp agents that follow up on every conversation until it reaches an outcome. One shared engine powers several products.

All repository documentation and code are in English. Product UI copy is in Spanish (Argentina).

## The products and their business goals

### inmo24x7: never lose a lead again

- **Customer:** real estate agencies, starting with large agencies and franchise networks that receive hundreds of inquiries from listing portals.
- **Problem:** inquiries arrive at night and on weekends, answers come hours later, and most leads go cold before anyone talks to them.
- **What it does:** replies on WhatsApp in seconds at any hour, qualifies the lead (operation, area, budget, financing), suggests matching properties from the agency's own listings, books visits, and hands off to an agent with a summary.
- **Success metric:** booked visits per month.

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
- **Status:** scope only; it is built after inmo24x7 on the same engine.

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

Open the gallery HTML files in a browser to browse every screen.

## Architecture

Dashed components and edges are planned.

```mermaid
flowchart TB
    subgraph Channels["Channels"]
        WHATSAPP["WhatsApp<br/>Meta Cloud API<br/>(planned)"]
        SIMULATOR["Web chat simulator<br/>(planned)"]
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

    subgraph Core["packages/core"]
        TENANCY["Tenancy"]
        IDENTITY["Identity<br/>(planned)"]
        MESSAGING["Messaging<br/>(planned)"]
        CONVERSATION["Conversation<br/>(planned)"]
    end

    PORT["AgentRuntime port<br/>(planned)"]
    LANGGRAPH["LangGraph runtime<br/>(planned)"]
    CHECKPOINTER["Postgres checkpointer<br/>(planned)"]

    subgraph Data["Data and identity"]
        POSTGRES["Postgres<br/>local development"]
        SUPABASE["Postgres on Supabase<br/>(planned)"]
        AUTH["Supabase Auth<br/>(planned)"]
    end

    ARCA["ARCA<br/>(planned)"]
    MERCADO_PAGO["Mercado Pago<br/>(planned)"]

    WHATSAPP -.-> MESSAGING
    SIMULATOR -.-> CONVERSATION

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
    API -.-> IDENTITY
    API -.-> MESSAGING
    API -.-> CONVERSATION
    CC_API -.-> TENANCY
    CC_API -.-> IDENTITY
    CC_API -.-> MESSAGING
    CC_API -.-> CONVERSATION

    CONVERSATION -.-> PORT
    PORT -.-> LANGGRAPH
    LANGGRAPH -.-> CHECKPOINTER
    CHECKPOINTER -.-> POSTGRES
    TENANCY --> POSTGRES
    POSTGRES -.-> SUPABASE
    IDENTITY -.-> AUTH
    AUTH -.-> SUPABASE
    CC_API -.-> ARCA
    CC_API -.-> MERCADO_PAGO

    classDef planned fill:#ffffff,stroke:#8b8b8b,stroke-width:1px,stroke-dasharray: 5 5,color:#666666;
    class WHATSAPP,SIMULATOR,CC_WEB,CC_BACKOFFICE,CC_CLIENT,CC_API,IDENTITY,MESSAGING,CONVERSATION,PORT,LANGGRAPH,CHECKPOINTER,SUPABASE,AUTH,ARCA,MERCADO_PAGO planned;
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

> **Security warning:** the API has no authentication until milestone 2. Do not deploy it publicly before then.

## Start

```bash
uv run --all-packages python scripts/dev.py
```

The command installs dependencies, starts Postgres, applies migrations, and starts the API and both panels. Press `Ctrl+C` to stop everything.

- Panel: http://localhost:5173
- Backoffice: http://localhost:5174
- API: http://localhost:8001
- API documentation: http://localhost:8001/docs
- Readiness: http://localhost:8001/health/ready

Local Postgres uses port 5433 to avoid conflicts with other databases.

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
| `APP_VERSION` | `0.1.0` | API, Docker | Version returned by readiness. Passed as a Docker build argument. |
| `GIT_COMMIT` | `unknown` | API, Docker | Commit returned by readiness. Passed as a Docker build argument. |
| `BUILD_DATE` | `unknown` | API, Docker | Build date returned by readiness. Passed as a Docker build argument. |

Supabase and Meta variables are added in milestones 2 and 3. The repository contains no real secrets.

Only the development script loads `.env` into API processes. When using the manual commands, export the variables in your shell.

## Tests and lint

The API integration tests use a real Postgres database and build its schema by running the Alembic migrations. Locally, make sure the compose database is running:

```bash
docker compose up -d --wait db
uv run --all-packages pytest
```

Fast unit tests use in-memory repositories. CI runs the API tests against a Postgres service container.

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
scripts                            local startup and type generation
```

## Images

On every push to the repository's default branch, after tests pass, CI builds and pushes amd64 + arm64 images for the API, web, and backoffice to GitHub Container Registry. Images use `latest` and `sha-<commit>` tags. The API receives `APP_VERSION`, `GIT_COMMIT`, and `BUILD_DATE`; the panels receive `VITE_API_URL` from the required `INMO24X7_API_URL` repository variable. Frontend image builds fail when it is missing.

Run the API image with `APP_ENV=production`, `DATABASE_URL`, and `CORS_ORIGINS` set.

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
