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
- Core revisions always chain to the core head, never to a product revision, so every new core revision creates a second head. Right after adding one, add a product merge revision with an empty upgrade whose `down_revision` is (current product head, new core head), as `inmo_0003` (core `0008`) and `inmo_0004` (core `0009`) do. Never rewrite a published revision.
- `tests/test_migrations.py` asserts that the graph has exactly one head, so a forgotten merge fails CI.
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
  requested → visit confirmed; visit confirmed → human requested (the team cancelled the
  visit). Visit confirmed is set only by the team. Every change is kept in
  `lead_status_changes`.
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

### The inbox (S6): takeover, team replies and visits

- **Control flag.** A thread has `control` (`agent` | `human`), `controlled_by_profile_id`
  and `control_changed_at` (Conversation context). `take_over` and `release` are domain
  functions that also return a system message for the transcript ("Ana tomó la
  conversación", "Ana devolvió la conversación al agente", with the profile's display name,
  else the email). Taking over a conversation someone else has moves control to the caller
  (the panel asks first).
- **Where it is checked.** `HandleIncomingMessage` reads the thread after taking the
  per-thread advisory lock, the same lock `TakeOverThread`, `ReleaseThread` and
  `AddTeamMessage` take. A takeover that races a running turn waits for it to commit; any turn
  after it sees `human`, stores the visitor's messages and returns without running the agent
  (`HandledTurn.agent_paused`). This holds for the simulator, the WhatsApp debounced job (also
  one queued before the takeover, since the check runs when the job does) and media, which get
  no fixed reply. `RecordLeadTurn` only touches the lead's activity on a paused turn.
- **Team replies** are `human` messages with `author_profile_id`. On WhatsApp they go through
  the same `QueueOutbound` and `whatsapp.send` job as the agent's; outside the 24-hour window
  they are refused (`outside_service_window`) before anything is stored. In the simulator they
  are only stored, and the Probalo chat polls while the thread is taken over. Only the person
  in control can reply (`conversation_not_taken`); owner, manager and agent can act, viewers
  only read.
- **Back to the agent.** The model reads recent transcript lines labelled `cliente`,
  `agente`, `equipo` and `evento` (prompt `extract.v3`), and the first turn after a release
  also reads the visitor's messages the agent never saw (sent while the team had it), so it
  does not ask again what the lead already told the team.
- **Confirm and cancel.** Confirming (optionally at another future time) sets the visit and
  the lead to confirmed, writes "Ana confirmó la visita" and tells the lead, all in one
  transaction plus the send job: free text inside the window, the connection's
  visit-confirmation template (name, address, day and time) outside it, or nothing to send in
  the simulator. Without a template outside the window it fails with
  `template_not_configured` before writing anything. Confirming twice is a no-op. Cancelling
  moves the lead back to human requested; its optional message is free text, so only inside
  the window.
- **Needs attention** ("Para atender") is defined once, on the `Lead`: status visit proposed
  or human requested, and no team reply since the hand-off (`last_human_reply_at`). A
  confirmed visit never needs attention. The repository mirrors it as one SQL expression and a
  test checks they agree. The tab is ordered by urgency: human requested first, then the
  soonest proposed visit, then the oldest hand-off. "Visitas" orders by visit time; "Todas" by
  last activity.
- **Search and export.** `leads.search_text` holds name, contact (also as bare digits) and
  answers, lowercase and without accents, so the search is a `LIKE` on one column; a query
  that looks like a phone is normalized to E.164 digits first. The CSV export uses the list's
  filters and order, `;` and a UTF-8 BOM (Excel in es-AR), one column per configured question,
  at most 5,000 rows; only the row count is logged.

### Dashboard KPIs (S5)

`dashboard/domain/kpis.py` defines them; the queries only fetch rows. All of them count real
leads only (never simulator tests) from Monday 00:00 in the business's timezone until now.

- **Consultas recibidas**: leads created this week (a lead starts at the visitor's first
  message); **fuera de horario**: those whose first message came outside the team's hours.
- **Calificadas**: leads this week with every enabled one of operation, zone and budget
  answered.
- **Visitas agendadas**: visits created this week that are proposed or confirmed (cancelled
  ones do not count), with how many are confirmed.
- **Respuesta promedio**: the average, over inbound bursts this week, of the time from the
  burst's first message to the agent's first reply (when WhatsApp accepted it, else when it
  was stored). Bursts the agent never answered (taken over) are left out; null without data.
- **Para atender hoy**: up to five leads in the attention order, topped up with the newest
  ones still qualifying.

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
  gets 200. A connection in error still receives: the messages are answered and the replies
  wait for the reconnection. `account_update` changes are applied too (see below), and every
  request is counted per hour (`webhook_counters`: received, signature rejected) for Salud del
  sistema. Status notifications update our outbound parts by wamid, only forward
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
  otherwise the part fails with `outside_service_window`. Templates are the way to write
  outside it: the connection's test template (`hello_world` on Meta test numbers) and its
  visit-confirmation template (`visit_template_name`, see the README), which the send job lets
  through after 24 hours.
- **Senders** sit behind `WhatsAppSender`: `CloudApiSender` (httpx, `META_GRAPH_API_VERSION`,
  v26.0 by default), `LogSender` for local development (fake wamids; simulated sent → delivered
  → read go through the same status code as Meta's), and a recording fake in tests (the Graph API
  is mocked at the HTTP level). Each connection stores which one it uses.
- **Connections** are one per tenant, created with Embedded Signup (below) or by hand in the
  backoffice (the fallback); both write the same row. The access token
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

### Embedded Signup (S4)

```text
panel: FB.login(config_id, response_type=code) ─▶ code (30 s) + WA_EMBEDDED_SIGNUP FINISH
       {waba_id, phone_number_id, business_id} ─▶ POST /whatsapp/embedded-signup (both at once)
API:   exchanged ─▶ subscribed ─▶ registered ─▶ connected        (whatsapp_signups.step)
       oauth/access_token   /{waba}/subscribed_apps   /{number}/register   GET /{number}
```

- **One use case, resumable.** `CompleteEmbeddedSignup` (core Messaging) saves the progress after
  each step: the business token encrypted like any access token, and a 6-digit PIN generated
  once per tenant (encrypted) for `register`. A failure returns `502 whatsapp_signup_failed` with
  the step and Meta's code, and the progress stays, so "Reintentar configuración" (panel or
  backoffice) continues from that step without Meta's popup. Only a failed code exchange needs
  the popup again (the code lives 30 seconds): `409 whatsapp_signup_restart`.
- **Idempotent.** A retry for a number that is already connected changes nothing and calls
  nobody. A new code starts over (new token, same PIN). A `phone_number_id` connected to
  another tenant is refused before any Meta call (`409 whatsapp_phone_number_taken`).
- **The last step** reads the number (display number, verified name, quality, name status) and
  tries the business verification (`GET /{business_id}?fields=verification_status`; Meta does
  not document it for every business token, so a failure means `unknown` and the panel shows
  both "Pendiente en Meta" links with neutral copy). It saves the connection as connected,
  writes the audit event and sends any replies that were waiting.
- **The web side** pairs FB.login's code with the `WA_EMBEDDED_SIGNUP` message (origin ending in
  `facebook.com`), whichever comes second, and posts both. `CANCEL`, `ERROR` and
  `FINISH_ONLY_WABA` are reported (`/embedded-signup/abandoned`, recorded in the audit log
  with the step and Meta's code) and explained in Spanish.

### Connection health

- **Meta errors** are classified once in core (`messaging/domain/meta_errors.py`): Meta's code →
  a stable internal code and a kind (auth, account, throttle, recipient, template,
  registration, request, unknown). The product owns the Spanish copy per internal code
  (`inmo24x7_api/whatsapp_errors.py`: title, what happened, what to do, and a technical line
  for admins). The status endpoints return it as data, so the panel and the backoffice show
  the same words; unknown codes get a generic message and the code only for admins.
- **States.** `connected` → `error` (with `last_error_code` and `failing_since`, kept from the
  first failure) → `connected` again. `ConnectionHealth` is the only place that moves them and
  writes the audit events (system failures at most once per tenant, code and hour).
- **Auth errors stop sending at once.** An auth error (190, 0, 3, 10, 200–299, 131005) or a
  blocking account error from a send, a read receipt or a Graph call marks the connection in
  error. The send job marks that part and the rest `waiting_connection` and finishes: there is
  no retry loop against a dead token, and later send jobs wait too. Throttling still retries
  with backoff; a recipient or template error fails only that part.
- **Reconnecting** (Embedded Signup, the manual form, a successful "Probar conexión" or health
  check, or an `account_update` that reinstates the account) puts the waiting parts back in
  the queue and sends them with one job, in conversation order. The 24-hour window still
  applies, so a reply that waited too long fails with `outside_service_window`.
- **The 6-hour check.** `whatsapp.health_sweep` runs once per 6-hour slot (the worker enqueues
  the current slot at start, each run chains the next; the dedupe key keeps it to one) and
  enqueues one `whatsapp.health_check` per Cloud connection of an active tenant. The check
  stores quality, name status and business verification; an auth error puts the connection in
  error, and a success clears an auth error.
- **`account_update`.** `PARTNER_APP_UNINSTALLED` and `PARTNER_REMOVED` (the customer removed
  our access), `ACCOUNT_DELETED` and `ACCOUNT_OFFBOARDED` put the connection in error;
  `DISABLED_UPDATE` disables or reinstates; `ACCOUNT_RECONNECTED` recovers an offboarded number;
  `PARTNER_CLIENT_CERTIFICATION_STATUS_UPDATE` updates the business verification. Restrictions
  and violations are recorded only: a send that is really blocked fails with its own code.

### Audit log

`audit_events` (core Tenancy) records what happened to a business: sign-up and owner claim,
agent config saved (version), properties imported (counts), WhatsApp connected, disconnected,
in error, recovered, signup failed or abandoned, Meta account updates, send failures,
suspension and reactivation, reconnect link sent, and businesses created by an admin. Each
event has an actor kind (`user`, `admin`, `system`) and, for people, the profile id. `details`
holds only ids, counts, codes and versions: the domain rejects any other key, so names,
emails, phones, message text and the suspension reason never land there. Repeated system
failures carry an hourly dedupe key. S9 "Actividad" shows the latest 20.

### Suspension and plans

- **Suspend** (admin, with a reason kept on the tenant) blocks the panel API with
  `403 tenant_suspended` in `current_profile` (only `/me` and sign-up skip the check, so the
  panel can show "Tu cuenta está suspendida"). Inbound WhatsApp messages are stored but never
  answered (no agent, no read receipt), queued sends fail with `tenant_suspended`, and the lead
  emails, the reconnect email and the health checks skip the tenant. Nothing is deleted;
  reactivating resumes everything with the next message.
- **Plans** are read-only for the MVP: trial ("Prueba · N días" from `trial_ends_at`) and pro,
  both with 1,000 conversations a month. A conversation this month is a WhatsApp thread with
  at least one inbound message since the 1st (Buenos Aires time); the simulator does not count.
  No enforcement and no billing yet.
- **"Dar de alta un negocio"** creates the tenant, its settings and onboarding, and an owner
  claim for an email. The first sign-up with that email joins the business as owner instead of
  creating another one.

### Backoffice (S8, S9)

`inmo24x7_api/backoffice/` reads one row per business in SQL (owner, onboarding facts,
WhatsApp, leads in 7 days) and applies pure rules from `backoffice/domain/rules.py` for the
WhatsApp badge, "Necesitan ayuda" (WhatsApp in error, onboarding unfinished for more than
48 hours, or a trial ending within 3 days without WhatsApp), the filters, search and the KPIs.
It reads every business once per request and filters in Python, which is fine for the MVP's
hundreds of businesses; move the rules into SQL if that grows to thousands. Platform-admin
tenants are left out. The detail masks the WABA (`•••• 1234`).

