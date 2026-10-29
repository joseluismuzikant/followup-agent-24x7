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

Milestone 1 implements Tenancy, Identity, Conversation, their endpoints, and both panels.

## Current boundaries

- Authentication is provided by Supabase Auth behind a `TokenVerifier` port; profiles carry roles and the platform-admin flag.
- The agent runs on LangGraph behind the `AgentRuntime` port; the simulator is its only channel
  until WhatsApp arrives with the messaging and connection flows.
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

The **Conversation** context in `packages/core` is product-agnostic and channel-agnostic.

- **Threads and transcripts.** A thread is identified by `ThreadKey`, whose canonical string
  `"{tenant_id}:{channel}:{visitor_id}"` is also the LangGraph `thread_id`. The
  `conversation_threads` and `conversation_messages` tables are the source of truth for
  transcripts (the inbox reads them). The checkpointer stores graph state only; transcripts
  are never read from checkpoints. Each thread pins the agent configuration version it
  started with, so a config change only applies to new threads (the simulator flags the old
  one as outdated).
- **`HandleIncomingMessage`** is the single entry point for every channel: lock the thread,
  get or create it, run the agent, then store the inbound and outbound messages. Nothing is
  written until the agent has replied.
- **Serialized turns.** A Postgres transaction-level advisory lock on the thread key makes two
  messages on the same thread run one after the other (WhatsApp delivers concurrently).
- **One transaction per turn.** The checkpointer writes on the request's own connection, so
  the lock, the transcript and the graph state commit or roll back together, and the graph
  runs with `durability="exit"`. A model timeout leaves no thread, message or checkpoint.
- **`AgentRuntime` port.** `LangGraphRuntime` runs any compiled graph the product supplies with
  `langgraph-checkpoint-postgres`; core contains no real estate logic. The graph contract is
  small: input `{"inbound", "outbox"}`, `GraphContext` (agent config, business, recent
  transcript, language model) as runtime context, and this turn's messages in `outbox`. Every
  other state key is the conversation state the API exposes.
- **Checkpointer tables** are created by Alembic migration `0005`, which ports the DDL of the
  pinned `langgraph-checkpoint-postgres` version and fills `checkpoint_migrations`; the API
  never calls `PostgresSaver.setup()`. Upgrading the checkpoint package needs a new migration
  with the new entries of its `MIGRATIONS` list.
- **The LLM port has two operations, not free-form chat.** `extract` reads values for the
  pending questions (plus name and contact) out of the latest message, and each value is
  validated against its question's kind before it reaches the state. `compose_reply` words a
  message for an intent the graph already chose. The graph decides the flow in code, so the
  model cannot skip a step, ask two things at once or invent a property. `LLM_MODEL` selects
  the provider (Anthropic, OpenAI, DeepSeek, or Kimi and MiMo through their OpenAI-compatible
  APIs); a deterministic `FakeLanguageModel` serves tests and local development.

The inmo24x7 **qualification graph** lives in the product (`apps/inmo24x7/api/.../leads`):
`extract → respond`, with `plan_turn` choosing the intents (greet, one question per
message in config order, sample property cards as soon as operation and zone are known and
before asking for name or contact, then a closing message). Prompts are versioned files in
`leads/prompts/` and the version is logged with every turn, along with tenant, thread key,
latency, model, token usage and the trace run id, never the message text. Property search is a
port; Day 3 uses sample CABA listings and Day 4 swaps in the tenant's own properties.

### Tracing (LangSmith)

Tracing is observability only: the agent behaves the same with it off, which is the default.

- **Turning it on.** `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`, with one project per
  environment (`inmo24x7-dev`, `inmo24x7-prod`, or `LANGSMITH_PROJECT`) and optionally
  `LANGSMITH_TRACING_SAMPLING_RATE`. The client is built once in `container.py`; a missing key
  or invalid setting logs a warning and leaves tracing off.
- **What is traced.** Each turn is one root run, `inmo24x7.lead_turn`, tagged with the product,
  `APP_ENV` and channel, with metadata `tenant_id`, `thread_key`, `channel`,
  `agent_config_version`, prompt versions, app version and commit. The LLM port calls are child
  runs `llm.extract` and `llm.compose_reply` (with the provider's own chat model runs under
  them), and the property search is a `property_search` child run.
- **From a message to its trace.** The runtime picks the root run id up front and stores it on
  the turn's outbound messages (`conversation_messages.trace_run_id`); the per-turn log line
  carries it too. With `LANGSMITH_UI_URL` set, backoffice simulator messages link to the run
  ("Ver traza"); the panel never shows the link.
- **Personal data.** Lead messages hold names, phone numbers, emails and DNIs. Unless
  `LANGSMITH_REDACT_PII=false`, the client's anonymizer masks emails, Argentine phone numbers
  (with or without +54 9, area code or 15) and DNI-like numbers in every input and output
  before it leaves the process. For full hiding in production, set `LANGSMITH_HIDE_INPUTS`
  and `LANGSMITH_HIDE_OUTPUTS`.
- **Never in the way.** Runs are posted from a background thread and LangSmith errors are
  logged, not raised, so tracing cannot fail or slow a turn. Every invocation runs inside
  `tracing_context`, which also forces tracing off when it is not configured, whatever the
  environment says. Pending runs are flushed on API shutdown. Tests and CI force tracing off.
- Prompts stay as versioned files in the repo (no LangSmith prompt hub); datasets and
  evaluations come later.
