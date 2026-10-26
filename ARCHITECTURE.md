# Architecture

Monorepo with a shared engine and multiple products. All code, names, comments, and documentation are in English; product UI copy is in Spanish.

## Layers

Each context has three folders:

- `domain/`: entities, value objects, and repository contracts. Pure Python.
- `application/`: use cases.
- `infrastructure/`: SQLAlchemy, WhatsApp, LangGraph, FastAPI, and other adapters.

`domain` never imports from `application` or `infrastructure`. If both products need a piece, it belongs in `packages/core`; otherwise, it stays in the product.

## Contexts

In `packages/core`:

- **Tenancy**: customers, plans, onboarding, notifications, and audit log.
- **Identity**: profiles, roles, and global administration.
- **Messaging**: WhatsApp Cloud API and Embedded Signup.
- **Conversation**: follow-up threads, agent runtime, and human handoff.

In `apps/inmo24x7/api`:

- **Leads**: qualification and property visit coordination.
- **Properties**: property import and validation.

Milestone 1 implements Tenancy, its endpoints, and both panels.

## Current boundaries

- No authentication yet: Supabase arrives with onboarding.
- **Do not deploy the API publicly before milestone 2.** There is no authentication or authorization yet; every endpoint is open.
- No LangGraph or WhatsApp yet: they arrive with the agent and connection flows.
- API integration tests run against a dedicated Postgres test database. Core unit tests use in-memory repositories.

## Migrations

There is one database and one Alembic version table.

- Core revisions live in `packages/core/migrations/versions`.
- Product revisions live in each product API's `migrations/versions`.
- The product API's Alembic configuration lists both version locations.
- Running migrations from any product applies the core revisions plus that product's revisions.

Core tables are migrated from core. Product tables are migrated from the product that owns them.

## Composition root

The product API is the composition root.

- Core routers receive use-case factories as dependencies.
- Core HTTP adapters do not build repositories or sessions.
- The product API's `container.py` wires sessions, SQLAlchemy repositories, and use cases.
- `main.py` assembles the application, middleware, health checks, and routers.

## API conventions

Errors are stable machine-readable codes, not user-facing text:

```json
{"code": "tenant_slug_taken"}
```

Each frontend maps those codes to Spanish messages. Validation, HTTP, domain, and readiness errors follow the same shape.

Every response carries an `X-Request-ID` header. Logs are JSON emitted through the standard library, and include the request id.

`GET /health` is liveness. `GET /health/ready` checks Postgres and returns the application version, commit, and build date.

## UI and API client

Both frontends use `@followup/ui` and `@followup/api-client-inmo24x7`. The client package owns the generated OpenAPI types and the `openapi-fetch` client. CI regenerates the schema and fails on drift.

## Agent

When added, conversation state will live in LangGraph with the Postgres checkpointer and `thread_id = tenant_id:channel:visitor_id`. Tools will be declared once and each will have a tested handler. The graph will control the flow; the LLM will not decide it through prompt rules. The same agent will serve WhatsApp and the simulator through the `AgentRuntime` port.
