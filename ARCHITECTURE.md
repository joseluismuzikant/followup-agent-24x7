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

Milestone 1 implements Tenancy, Identity, their endpoints, and both panels.

## Current boundaries

- Authentication is provided by Supabase Auth behind a `TokenVerifier` port; profiles carry roles and the platform-admin flag.
- No LangGraph or WhatsApp yet: they arrive with the agent and connection flows.
- API integration tests run against a dedicated Postgres test database. Core unit tests use in-memory repositories.

## Onboarding, business settings and agent configuration

All three live in the Tenancy context of `packages/core`, because every product needs them:

- **Onboarding** is one record per tenant: the furthest wizard step reached, the completed
  steps with timestamps, and `finished_at`. Use cases only move it forward; revisiting a step
  to edit it never uncompletes anything.
- **Business settings** (not versioned) hold the business type, timezone, the team's weekly
  schedule and the notification emails. `is_within_team_hours` is a pure domain function so
  KPIs and the agent share one definition of "out of hours".
- **Agent configuration** is versioned (`agent_config_versions`, highest version is current).
  A save creates a version only when the config changed. The domain object is product-agnostic:
  name, tone, after-hours mode and an ordered list of qualification questions with stable keys.
  Questions are data, so the graph reads the list instead of hard-coding it.
- **Defaults are injected by the product.** The inmo24x7 API builds `SetupDefaults` (agent
  name, tone, the five real estate questions, team hours) in `defaults.py` and passes them to
  the use cases from `container.py`. Core knows nothing about real estate, so Cuentas Claras
  can start from its own defaults.
- **Setup checklist** is computed on the server from facts (`SetupFacts`). Facts owned by later
  days come from `SetupFactProviders`, which return false today; each day plugs in its own
  provider in `container.py`. The panel shows five items and the full fact set is available
  to the backoffice.

Writes to these resources need the owner or manager role; reads are open to every role of the
tenant. The tenant always comes from the caller's profile, never from the request.

## Migrations

There is one database, one root `alembic.ini`, and one Alembic version table.

- The root `migrations` directory contains the environment and revision template.
- Version locations include the core chain and every product chain.
- Core revisions live in `packages/core/migrations/versions`.
- Product revisions live in each product API's `migrations/versions`.
- Product revision chains must set `down_revision` to the current core head, so every product chain depends on core.
- Run `uv run alembic upgrade head` from the repository root to apply all locations.
- API integration tests build their schema by running these migrations.
- The API image contains the root configuration, so deployments run `alembic upgrade head` once in a one-off container before starting the new API version.

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
