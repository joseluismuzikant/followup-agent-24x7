# followup-agent-24x7

Platform for WhatsApp agents that follow up on every conversation until it reaches an outcome.

- **inmo24x7**: qualifies real estate leads and books property visits. This is the first product.
- **Cuentas Claras**: invoice collection for service companies. Only the scope is defined.

Current state: **milestone 1**, the foundation for the panel, API, and tenancy.

All repository documentation and code are in English. The product UI is in Spanish (Argentina).

## Requirements

- Docker with Compose.
- [uv](https://docs.astral.sh/uv/).
- Node.js 22 or newer. Corepack, included with Node, provides `pnpm`.

## Start

```bash
uv run --all-packages python scripts/dev.py
```

The command installs dependencies, starts Postgres, applies migrations, and starts
the API and both panels. Press `Ctrl+C` to stop everything.

- Panel: http://localhost:5173
- Backoffice: http://localhost:5174
- API: http://localhost:8001
- API documentation: http://localhost:8001/docs

Local Postgres uses port 5433 to avoid conflicts with other databases.

### Manual start

```bash
uv sync --all-packages
corepack pnpm install --frozen-lockfile
docker compose up -d --wait db
uv --directory apps/inmo24x7/api run alembic upgrade head
```

Then, in separate terminals:

```bash
uv --directory apps/inmo24x7/api run uvicorn inmo24x7_api.main:app --reload --port 8001
corepack pnpm --filter @inmo24x7/web dev
corepack pnpm --filter @inmo24x7/backoffice dev
```

## Environment variables

Copy `.env.example` to `.env` to change the defaults. The development script and
Vite read the root `.env`. Docker Compose also reads it automatically.

| Variable | Local default | Used by | Description |
| --- | --- | --- | --- |
| `POSTGRES_USER` | `followup` | Docker Compose | Initial local Postgres user. |
| `POSTGRES_PASSWORD` | `followup` | Docker Compose | Initial local Postgres password. |
| `POSTGRES_DB` | `followup` | Docker Compose | Local database name. |
| `DATABASE_URL` | `postgresql+psycopg://followup:followup@localhost:5433/followup` | API, Alembic | Postgres connection. In production it points to Supabase. Update it if you change the user, password, database, or port. |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:5174` | API | Allowed origins, separated by commas. |
| `VITE_API_URL` | `http://localhost:8001` | Web, backoffice | Public API URL. It is embedded in the panel builds. |

Supabase and Meta variables are added in milestones 2 and 3. The repository
contains no real secrets.

## Tests, lint, and types

```bash
uv run --all-packages pytest
corepack pnpm test

uv run ruff check .
uv run ruff format --check .
corepack pnpm lint
corepack pnpm typecheck

uv run --all-packages python scripts/generate_types.py
```

## API

```bash
curl http://localhost:8001/health
curl http://localhost:8001/tenants
curl -X POST http://localhost:8001/tenants \
  -H "Content-Type: application/json" \
  -d '{"name":"Inmobiliaria Sur"}'
```

## Structure

```text
apps/inmo24x7/api          FastAPI API
apps/inmo24x7/web          customer panel
apps/inmo24x7/backoffice   internal administration
apps/cuentas-claras        second product scope
packages/core              shared domain and application layer
packages/ui                shared React components
scripts                    local startup and type generation
```

## Images

Images support multiple architectures (amd64 and arm64):

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -f apps/inmo24x7/api/Dockerfile -t my-registry/inmo24x7-api:latest --push .
```

Use the same command with the `web` and `backoffice` Dockerfiles. The panels need
`--build-arg VITE_API_URL=https://api.example.com` at build time.

## License

TODO: choose a license before distributing this project.
