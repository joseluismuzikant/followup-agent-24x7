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
- **Messaging**: WhatsApp Cloud API: connections, the webhook pipeline and sending (Embedded
  Signup on Day 7).
- **Scheduling**: background jobs in Postgres and the worker that runs them.
- **Notifications**: email to the business behind an `EmailSender` port.
- **Conversation**: follow-up threads, agent runtime, and human handoff.

In `apps/inmo24x7/api`:

- **Leads**: one lead per conversation, S5 statuses, visit proposals and hand-off, plus the
  lead agent (graph, tools and prompts).
- **Properties**: the agency's listings, spreadsheet import and validation, and the property
  search the agent uses.

Both product contexts follow the same domain/application/infrastructure layout as core.

## Current boundaries

- Authentication is provided by Supabase Auth behind a `TokenVerifier` port; profiles carry roles and the platform-admin flag. See "Auth modes" for local development.
- The agent runs on LangGraph behind the `AgentRuntime` port; the simulator and WhatsApp are its
  channels, both through `HandleIncomingMessage`.
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
- Product revision chains must set `down_revision` to the current core head, so every product chain depends on core. The inmo24x7 chain starts at `inmo_0001` (properties and imports), whose `down_revision` is core `0006`, followed by `inmo_0002` (leads). Product revisions use their own ids (`inmo_NNNN`) so they never collide with core numbers.
- A later core revision chains to the core head (`0006`), never to a product revision, so it creates a second head. Add a merge revision in the product chain (`alembic merge`) so `alembic upgrade head` keeps a single head; never rewrite a published revision.
- Run `uv run alembic upgrade head` from the repository root to apply all locations.
- API integration tests build their schema by running these migrations.
- The API image contains the root configuration, so deployments run `alembic upgrade head` once in a one-off container before starting the new API version.

## Auth modes

`AUTH_MODE` (API) and `VITE_AUTH_MODE` (panels) choose how people sign in:

- **`supabase`**: Supabase Auth (Google or magic link) in the panels; the API verifies the JWT
  with the secret or the JWKS URL and checks the issuer `{SUPABASE_URL}/auth/v1`. This is the
  only mode allowed in production.
- **`dev`**: local development without any external service. The panels show a "Modo
  desarrollo" box; the session is the token `dev:<email>` in localStorage. The API's
  `DevTokenVerifier` accepts only that shape and maps the email to
  `uuid5(fixed namespace, email)`, so the same email is always the same user (the seed relies
  on it). `APP_ENV=production` with `AUTH_MODE=dev` stops the API at startup, and a
  production `vite build` with `VITE_AUTH_MODE=dev` fails, so a dev build can never ship.

Both panels hide the choice behind one `AuthProvider`/`useAuth`: an `AuthAdapter` with a
Supabase and a dev implementation. Pages only see `{ accessToken, email }`. The Supabase
client is created on first use, so dev mode never builds it, and empty `VITE_SUPABASE_*`
values count as unset.

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
  written until the agent has replied. Then it calls the product's **turn observers**
  (`TurnObserver.on_turn`) in the same transaction; inmo24x7 uses one to keep the lead in step.
- **System messages.** A graph may emit `{"author": "system"}` items (for example "El agente
  derivó la consulta a tu equipo"). They are stored in the transcript like any other message
  and are never sent to the lead by a channel.
- **Serialized turns.** A Postgres transaction-level advisory lock on the thread key makes two
  messages on the same thread run one after the other (WhatsApp delivers concurrently).
- **One transaction per turn.** The checkpointer writes on the request's own connection, so
  the lock, the transcript and the graph state commit or roll back together, and the graph
  runs with `durability="exit"`. A model timeout leaves no thread, message or checkpoint.
- **`AgentRuntime` port.** `LangGraphRuntime` runs any compiled graph the product supplies with
  `langgraph-checkpoint-postgres`; core contains no real estate logic. The graph contract is
  small: input `{"inbound", "outbox"}`, `GraphContext` (agent config, business with timezone
  and team hours, recent transcript, the time the message arrived, the language model and the
  product's tools) as runtime context, and this turn's messages in `outbox`. Every other state
  key is the conversation state the API exposes.
- **Tools are declared once in a `ToolRegistry`** (core, product-agnostic): a name, an input
  schema (a frozen dataclass) and a handler. The graph calls `context.tools.call(name, input)`
  when its code decides to; the model never picks a tool. The runtime wraps every handler so
  each call is a child run of the traced turn named after the tool.
- **Checkpointer tables** are created by Alembic migration `0005`, which ports the DDL of the
  pinned `langgraph-checkpoint-postgres` version and fills `checkpoint_migrations`; the API
  never calls `PostgresSaver.setup()`. Upgrading the checkpoint package needs a new migration
  with the new entries of its `MIGRATIONS` list.
- **The LLM port has two operations, not free-form chat.** `extract` reads values for the
  pending questions (plus name and contact) out of the latest message, which of the offered
  choices the person picked (a property card or a visit slot, by position, address or label;
  only ids that were offered are accepted), and whether they asked for a person. Each value is
  validated against its question's kind before it reaches the state. `compose_reply` words a
  message for an intent the graph already chose. The graph decides the flow in code, so the
  model cannot skip a step, ask two things at once or invent a property. `LLM_MODEL` selects
  the provider (Anthropic, OpenAI, DeepSeek, or Kimi and MiMo through their OpenAI-compatible
  APIs); a deterministic `FakeLanguageModel` serves tests and local development.

The inmo24x7 **lead graph** lives in the product (`apps/inmo24x7/api/.../leads`):
`extract → respond`, with `plan_turn` choosing the intents in code:

1. Greet, then one question per message in config order.
2. Property cards as soon as operation and zone are known, always before asking for name or
   contact (`search_properties`).
3. When the lead picks a card, offer the next two visit slots for it (`propose_visit`); when
   they pick a slot, note it (status "Visita propuesta"), ask for name and contact if missing
   (`save_contact` validates and normalizes them), then hand off (`hand_off`).
4. A lead who did not pick anything is invited once to visit, then handed off.
5. "Quiero hablar con una persona" at any step hands off immediately ("Pidió hablar con
   alguien"). After a hand-off the agent answers politely and never proposes a visit again.

Card links come only from the search results, so they are the property's own listing link
(or a local sample page). Prompts are versioned files in `leads/prompts/` (`extract.v2`,
`reply.v2`; v1 is kept), and the versions are logged with every turn, along with tenant, thread
key, latency, model, token usage and the trace run id, never the message text.

### Leads

- **One lead per thread**, created by `RecordLeadTurn` (a turn observer) on the first inbound
  message and updated after every turn from the graph state: answers, name, contact, the
  visit picked, the hand-off and the own properties shown (`lead_property_matches`). Writing
  from the state keeps it idempotent. Simulator threads create test leads (`is_test`), hidden
  from Consultas unless asked for.
- **Statuses and transitions** are enforced by the `Lead` aggregate: qualifying → visit
  proposed or human requested; visit proposed → human requested or visit confirmed; human
  requested → visit confirmed. Visit confirmed is set by the team (Day 6). Every change is
  kept in `lead_status_changes`.
- **Slots** come from a pure domain function: the next two 30-minute slots at least two hours
  ahead that fit inside the team's hours, in the tenant's timezone. Out of hours the agent still
  proposes them and says the team confirms. A visit for a sample listing has no property id,
  only its label.

### Properties

- `properties` are unique per `(tenant_id, link)`: re-importing a link updates that property,
  and unchanged rows are not written. There is no delete: pausing hides a property from the
  agent. Search runs on a stored lowercase, accent-free copy of address and zone, so it needs
  no database extension.
- **Import** reads CSV (UTF-8 or Latin-1, comma or semicolon) and XLSX, up to 5 MB and 2,000
  rows, with the Spanish template headers. Each row is validated on its own, valid rows are
  saved even when others fail, and the failed rows are kept on the import record so the error
  CSV (original columns plus `error`) can be downloaded later. Row errors are written in
  Spanish on the server because they end up in that file.
- **Agent search** (`TenantPropertySearch`) uses the tenant's published properties with the
  same matching rules as before (operation, zone, rooms, budget in the same currency with a 25%
  over-budget allowance, no conversion). While the tenant has no published property it uses
  the sample fixture and the simulator shows the sample banner; once one is published the
  fixture is never used for that tenant.
- **Inquiries per property** count distinct non-test leads the agent showed it to.

### Tracing (LangSmith)

Tracing is observability only: the agent behaves the same with it off, which is the default.

- **Turning it on.** `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY`, and optionally
  `LANGSMITH_TRACING_SAMPLING_RATE`. Turns go to the LangSmith agent named by
  `LANGSMITH_AGENT_ID` and `LANGSMITH_AGENT_ENVIRONMENT` (an agent address); without them, to
  one project per environment (`inmo24x7-dev`, `inmo24x7-prod`, or `LANGSMITH_PROJECT`). The
  runtime always names the destination in code, so the SDK's own reading of those variables
  never competes with it. The client is built once in `container.py`; a missing key
  or invalid setting logs a warning and leaves tracing off.
- **What is traced.** Each turn is one root run, `inmo24x7.lead_turn`, tagged with the product,
  `APP_ENV` and channel, with metadata `tenant_id`, `thread_key`, `channel`,
  `agent_config_version`, prompt versions, app version and commit. The LLM port calls are child
  runs `llm.extract` and `llm.compose_reply` (with the provider's own chat model runs under
  them), and each tool call is a child run named after the tool (`search_properties`,
  `save_contact`, `propose_visit`, `hand_off`).
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

## Scheduling (jobs)

Work that must survive a restart and must not run inside a request is a **job** in the
`jobs` table (core `scheduling`; Day 9 extends it for reminders).

- **Enqueue in the caller's transaction**, so a job exists only if the work that created it
  committed. A `dedupe_key` (unique) drops a second job with the same key: one email per lead
  and kind, one processing job per WhatsApp message, one purge per day.
- **Claim with `FOR UPDATE SKIP LOCKED`**: two workers never get the same job. A claim sets
  `locked_until`; a job whose worker died is reclaimed when its lock expires.
- **Outcomes**: done; a failure retries with exponential backoff and jitter; past
  `max_attempts` the job is `dead` and logged as an error. A handler can also return
  `Reschedule` (not yet, without spending an attempt: the debounce) or `RetryLater` (keep the
  work done so far, retry the rest: a send interrupted by a 429).
- Claiming, running and recording the outcome are separate transactions, so delivery is
  at-least-once and handlers are idempotent.
- **One handler per kind** (`JobHandlers`), tested like the tool registry: every `NewJob(...)`
  in the code has exactly one handler.
- **The worker** is `python -m inmo24x7_api.worker`: `WORKER_CONCURRENCY` threads, each with its
  own sessions; SIGTERM lets running jobs finish. `dev.py` starts it; production runs the API
  image with that command.

## Messaging (WhatsApp)

### The pipeline

```text
Meta ─POST /webhooks/whatsapp─▶ verify signature ─▶ inbound event (unique wamid) ─▶ job
                                          (200 in ms; no model, no Meta call)
worker: whatsapp.process ─▶ debounce ─▶ one agent turn for the burst ─▶ outbound parts (queued)
worker: whatsapp.send ─▶ Cloud API, in order ─▶ wamid ─▶ statuses from Meta: sent/delivered/read
```

- **Webhook.** The signature (`X-Hub-Signature-256`, HMAC-SHA256 with `META_APP_SECRET`,
  constant-time compare) is checked over the raw body before parsing. Each message becomes a
  `whatsapp_inbound_events` row; the unique `wamid` makes the database drop Meta's retries. An
  unknown or disconnected `phone_number_id` is stored as `ignored` (with a warning) and still
  gets 200. Status notifications update our outbound parts by wamid, only forward
  (read > delivered > sent; failed keeps Meta's code).
- **Debounce and ordering.** Each event enqueues a processing job `INBOUND_DEBOUNCE_SECONDS`
  later. The job takes the thread's advisory lock (the same one as every turn), and while the
  newest pending event is younger than the debounce it reschedules itself; then it takes every
  pending event of the conversation in order and runs one turn. Each message is stored on its
  own in the transcript; the agent reads them joined. Later jobs of the burst find nothing.
- **Channel facts.** The thread key is `tenant:whatsapp:<wa_id>`. The visitor's number becomes
  the lead's contact, so the agent never asks for a phone on WhatsApp. A tapped reply button
  carries the slot id: `choice_id` is the same path the simulator's slot buttons use, and the
  graph accepts only ids it offered. Media (audio, images, ...) is stored with its type and gets
  a fixed reply without the model; reactions are ignored. Processed messages are marked read.
- **Why sending is a job.** The turn stores its replies and their rendered parts
  (`whatsapp_outbound`, `queued`) in the turn's transaction and enqueues one send job, so a Meta
  outage never rolls back a turn and a retry never sends a part twice (parts with a wamid are
  skipped). 429/5xx retry with backoff; permanent errors mark the part `failed` with Meta's code
  and the rest still goes out.
- **Rendering** is the product's: text (split above 4,096 characters), one message per property
  card (bold title, address, price, the over-budget note and the listing link with preview), visit
  slots as reply buttons (at most 3, titles of 20 characters, ids = slot ids). System messages
  such as the hand-off event are never sent.
- **The 24-hour window.** Free-form messages go only if the visitor wrote in the last 24 hours;
  otherwise the part fails with `outside_service_window`. `send_template` (the connection's
  template, `hello_world` on Meta test numbers) is the way to write outside it (Day 6 confirms
  visits with it).
- **Senders** sit behind `WhatsAppSender`: `CloudApiSender` (httpx, `META_GRAPH_API_VERSION`,
  v26.0 by default), `LogSender` for local development (fake wamids; simulated sent → delivered
  → read go through the same status code as Meta's), and a recording fake in tests (the Graph API
  is mocked at the HTTP level). Each connection stores which one it uses.
- **Connections** are one per tenant, created by hand in the backoffice today. The access token
  is encrypted with AES-256-GCM (`TOKEN_ENCRYPTION_KEY`), stored as `k1:<base64>` so keys can be
  rotated, and never returned or logged. Raw webhook payloads (personal data) are purged after
  30 days by a daily job; the rows and statuses stay.
- **Phones** are normalized with `phonenumbers`: E.164 stored, "+54 9 11 5555-0188" shown,
  replies always to the `wa_id` as Meta sent it.
- **Logs** carry ids, codes and timings, never message text, phone numbers or emails.

### New-lead email

`RecordLeadTurn` enqueues, in the turn's transaction and only for real leads (never simulator
tests), a hand-off email ("Nueva consulta", with the answers and the visit or the request) and a
"Consulta en curso" email 15 minutes after the first message, which is skipped if the lead was
handed off by then. Dedupe keys make it at most one of each per lead. They go to the tenant's
notification emails through SMTP (Mailpit locally), with a link to
`{PANEL_URL}/consultas?lead=<id>`.

