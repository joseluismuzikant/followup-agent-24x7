# Claude Code prompt — Day 3: conversation runtime and the Probalo simulator

Open Claude Code at the repo root on a fresh branch you create yourself (for example
`git checkout -b feature/day-3`), then paste everything inside the block. Claude will not
commit anything: you review the diff and commit yourself.

```text
You are working in the followup-agent-24x7 monorepo on Day 3 of docs/roadmap-mvp.md.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- You MAY run read-only git commands (git status, git diff, git log) to check your work.
- Leave every change uncommitted in the working tree. I review the diff and commit myself.
- At the end, give me a suggested commit split (which files go in which commit, with a
  commit message for each), but do not run it.

READ BEFORE PLANNING
README.md, ARCHITECTURE.md (especially "Agent" and "Onboarding, business settings and agent
configuration"), docs/roadmap-mvp.md (Day 3 and Day 4), docs/screens-spec.md (S3, S5's
"Probar el agente", S8 nav "Simulador", S9 "Probar su agente"). Then the Day 2 code:
packages/core/src/followup_core/tenancy (agent_config, business_settings, setup_checklist,
setup_facts, agent_setup), apps/inmo24x7/api/src/inmo24x7_api (container, main, auth,
defaults, agent_setup), apps/inmo24x7/web/src (pages/onboarding.tsx, components/
AgentSetupForm.tsx, lib/setup.ts) and apps/inmo24x7/backoffice/src.

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, the domain imports nothing outward,
container.py is the composition root, errors are stable codes {"code": "..."} mapped to
Spanish in the frontends, generated OpenAPI client in @followup/api-client-inmo24x7
(regenerate schema.ts), shared presentational components in @followup/ui. Code and docs in
English; UI copy and agent replies in Spanish (Argentina, voseo). The tenant always comes
from the caller's profile, except in admin endpoints that take it explicitly.

=====================================================================
PART 0 — Day 2 follow-ups
=====================================================================
0.1 Custom question keys must never be reused. Today the web computes custom_<n> from the
    current list, so deleting custom_2 and adding a question creates custom_2 again, and
    from Day 3 on old answers would attach to the new question. Make the server own keys:
    a new custom question is sent without a key and SaveAgentSetup assigns
    custom_<max ever used in any version of this tenant + 1>. A submitted custom_* key that
    never existed in a previous version is rejected (422 "questions_invalid"). Built-in keys
    come from the product defaults only. Update the web form and the tests.
0.2 Two simultaneous saves of the agent config hit the unique (tenant_id, version)
    constraint and return 500. Map that IntegrityError to 409 "agent_setup_conflict"; the
    web shows "Alguien más guardó cambios. Recargá para ver la última versión." Add a test.
0.3 Wizard step 4 copy must match S4 exactly:
    1. "Entrá con tu cuenta de Facebook" — "La que administra la página o el negocio de la
       inmobiliaria."
    2. "Elegí el número" — "Puede ser uno nuevo o el que ya usan. Si está en la app de
       WhatsApp Business, Meta te guía para pasarlo."
    3. "Confirmá con el código por SMS" — "Listo: nosotros configuramos todo lo demás y te
       mandamos un mensaje de prueba."
    Subtitle: "Se abre una ventana de Meta. Tarda unos 3 minutos y no necesitás saber nada
    técnico." The connect button itself stays out until Day 7.

=====================================================================
PART 1 — Day 3 goal
=====================================================================
Done when: in the wizard's Probalo step I chat with my agent, it introduces itself with the
configured name, business and tone, asks the enabled qualification questions one per
message, shows sample property cards before asking for personal data, and fills "Lo que el
agente ya sabe" as I answer. I stop the API, start it again, reload the page, and the
conversation and the state panel are exactly where they were. "Reiniciar" starts a new
conversation.

ARCHITECTURE
1. Conversation context in packages/core/src/followup_core/conversation (product-agnostic):
   - Domain: Channel (simulator | whatsapp), ThreadKey with the canonical string
     "{tenant_id}:{channel}:{visitor_id}", Thread (key, tenant_id, channel, visitor_id,
     agent_config_version, status open|closed, created_at, last_message_at), Message
     (thread, direction inbound|outbound, author visitor|agent|human|system, text, optional
     structured payload such as property cards, created_at), repository contracts.
   - AgentRuntime port: handle(thread, agent_config, business context, inbound message)
     -> AgentTurn(outbound messages, state snapshot). It knows nothing about channels.
   - Application: HandleIncomingMessage (channel-agnostic: get or create the thread, pin the
     current agent config version at thread creation, append the inbound message, call the
     runtime, append outbound messages, update last_message_at), GetThread (transcript +
     state), StartNewThread (used by Reiniciar).
   - Serialize turns per thread with a Postgres transaction-level advisory lock on the
     thread key, so two messages in the same thread never run the graph at the same time
     (WhatsApp on Day 5 depends on this).
   - Our own threads/messages tables are the source of truth for transcripts (the Day 6
     inbox reads them). The checkpointer stores graph state only; never read transcripts
     from checkpoints.
2. LangGraph runtime in core infrastructure: implements AgentRuntime, uses
   langgraph-checkpoint-postgres (PostgresSaver on psycopg 3) with thread_id = ThreadKey
   string. Exposes the graph state snapshot through the port.
   - Checkpointer tables are created by an Alembic migration (call the saver's setup from
     the migration, or port its DDL), never by the API at startup, so deploys stay
     "alembic upgrade head" only. Pin the exact langgraph and checkpoint package versions
     (check current releases on PyPI) and note in ARCHITECTURE.md that upgrading the
     checkpoint package needs a new migration.
   - The graph is supplied by the product: core runs any compiled graph; it does not
     contain real estate logic.
3. LLM port with two narrow operations instead of free-form chat, so the graph keeps
   control of the flow (ARCHITECTURE.md: the LLM does not decide the flow):
   - extract(questions to fill, recent transcript, latest message) -> {key: value} with
     values validated against each question's kind (choice options, number, money in ARS or
     USD, boolean, text), plus visitor name and contact if given.
   - compose_reply(intent, facts, tone, agent name, business name, language rules) -> text.
   Real adapter via LangChain init_chat_model with LLM_MODEL (provider:model string, e.g.
   "anthropic:claude-sonnet-5-5") and the provider's API key from the environment, with a
   timeout and one retry. A FakeLlm adapter with deterministic rules (simple keyword/regex
   extraction and template replies) for tests and for local development without a key;
   log a startup warning when it is active. Production fails at startup if LLM_MODEL or the
   key is missing. On LLM timeout or provider error the endpoint returns 503
   "agent_unavailable"; no partial turn is stored.
   Prompts live as versioned files (e.g. apps/inmo24x7/api/src/inmo24x7_api/leads/prompts/
   extract.v1.md, reply.v1.md) and the version used is logged per turn.
4. The inmo24x7 basic qualification graph in apps/inmo24x7/api/.../leads/graph.py:
   - State: answers keyed by the question keys of the pinned agent config, visitor name,
     contact, properties already shown, last intent.
   - Flow decided by code: greet on the first turn («Hola! Soy {agent}, de {business}...»),
     run extraction on every inbound message, then pick the next enabled question in the
     configured order that has no answer. Exactly one question per outbound message.
   - As soon as operation and zone are known (budget and rooms if they are enabled and
     known), send up to 3 property cards BEFORE asking for name or contact. Over-budget
     items carry the note "un poco más de tu presupuesto".
   - Custom questions (custom_*) are asked and stored like the others but never used to
     filter properties.
   - When all enabled questions are answered and contact is known, reply with a closing
     message that a person from the team will follow up. Visit proposals and hand-off are
     Day 4; do not build them.
   - Tone: warm / professional / formal change wording only, never the flow.
5. Sample properties: behind a PropertySearch port in the product (search by operation,
   zone, max budget, rooms; returns title, address, operation, zone, price + currency,
   rooms, link). Today's adapter is a static fixture of ~12 realistic CABA listings
   (Palermo, Belgrano, Caballito, Villa Urquiza, Núñez; rent in ARS, sale in USD) flagged
   is_sample=true, with links to a local placeholder page, never invented external URLs.
   Day 4 swaps in the database adapter. The simulator shows the sample banner while the
   tenant has no own properties (use the existing own_properties fact provider).
6. Setup facts: plug in the agent_tested provider — true once the tenant has a simulator
   thread with at least one inbound message.
7. LangSmith tracing (observability only; the app must work identically with it off):
   - Tracing is controlled by environment variables only: LANGSMITH_TRACING,
     LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_ENDPOINT (check the current LangSmith
     docs for exact names before using them). Off by default. One project per environment
     (e.g. inmo24x7-dev, inmo24x7-prod); production may set LANGSMITH_TRACING_SAMPLING_RATE.
   - Every graph invocation passes run_name ("inmo24x7.lead_turn"), tags (product, channel,
     APP_ENV) and metadata: tenant_id, thread_key, channel, agent_config_version, prompt
     versions, app version and commit. LLM port calls appear as child runs named
     "llm.extract" and "llm.compose_reply"; wrap the PropertySearch call as a child run too.
   - Store the root run id of each turn on its outbound messages (nullable column) and
     include it in the per-turn log line, so a support case can jump from a message to its
     trace. Add a backoffice-only link "Ver traza" on simulator messages when a run id
     exists and LANGSMITH_UI_URL is configured; no link otherwise.
   - Personal data: lead messages contain names, phone numbers and emails. Configure the
     LangSmith client once in the composition root with an anonymizer that masks emails,
     phone numbers (Argentine formats, with or without +54 9) and DNI-like numbers before
     anything is sent. Add LANGSMITH_REDACT_PII (default true; when true the anonymizer is
     on) and document LANGSMITH_HIDE_INPUTS / LANGSMITH_HIDE_OUTPUTS for production if
     full hiding is wanted. Unit-test the anonymizer.
   - Flush pending traces on API shutdown (FastAPI lifespan), and never let a LangSmith
     error, timeout or missing key fail or slow down a turn.
   - Tests and CI run with tracing forced off (set in conftest and CI env), so no test
     makes network calls to LangSmith.
   - Prompts stay as versioned files in the repo; do not use the LangSmith prompt hub.
     LangSmith datasets and evaluations are out of scope today.

API
Tenant-scoped (any role can use the simulator; visitor_id = the caller's profile id plus a
per-user thread counter so Reiniciar creates a new ThreadKey):
- GET  /simulator → {thread: {key, agent_config_version, created_at}, messages: [...],
  known: [...], uses_sample_properties: bool, config_outdated: bool}. Creates nothing.
- POST /simulator/messages {text (1–1000 chars)} → {messages: [new outbound messages],
  known: [...]}.
- POST /simulator/reset → starts a new thread; returns the empty GET /simulator shape.
"known" is the state panel as typed rows in display order: one per ENABLED question in the
pinned config order, then name, then contact: {key, label, value: string | null}. Values are
formatted on the server for display (e.g. "Alquiler", "Hasta $900.000", "USD 120.000", "Sí").
Out-of-config answers are not shown. config_outdated is true when the pinned version is
older than the tenant's current agent config.
Admin (require_platform_admin, for S8/S9 "Probar su agente"):
- GET/POST /admin/tenants/{tenant_id}/simulator, .../messages, .../reset with the same
  shapes, visitor_id = admin profile id. 404 "tenant_not_found" for unknown tenants.
Guard rail: max 300 simulator inbound messages per tenant per day → 429
"simulator_limit_reached".
Do not log message text (it is personal data); log tenant, thread key, latency, model,
prompt version and token usage per turn.

WEB
- @followup/ui: a presentational ChatSimulator (header with avatar initial, "{agent} ·
  {business}", "Responde al instante", "Reiniciar"; bubbles for visitor/agent/system;
  PropertyCard with title, address, price, "Ver fotos" link and the over-budget note;
  typing indicator; input "Escribí un mensaje…" + "Enviar"; Enter sends, Shift+Enter adds a
  line) and a KnownFactsPanel ("Lo que el agente ya sabe", "Pendiente" for null). No data
  fetching inside @followup/ui.
- Wizard step 3 (replaces the placeholder), copy per S3: "Paso 3 de 5 · Probalo", title
  "Escribile como si fueras un cliente", subtitle "Así va a responder en WhatsApp. Todavía no
  conectaste nada: esto es una prueba privada."; the sample banner "Está usando propiedades
  de ejemplo" / "Subí tu listado en CSV o Excel y el agente va a mostrar solo tus
  propiedades." / "Subir mis propiedades" (links to /propiedades); buttons "← Ajustar el
  agente" and "Me gusta, conectar WhatsApp" (keeps the existing advance). If
  config_outdated: "Cambiaste tu agente. Reiniciá la conversación para probar los cambios."
- Panel: "Probar el agente" button on Inicio opens /probar (same simulator inside the app
  shell). Mobile: the state panel moves under the chat.
- Optimistic visitor bubble while the request runs; on 503 show "Tu agente no pudo responder
  ahora. Probá de nuevo." and let me resend; on 429 show the daily limit message.
- Backoffice: "Simulador" nav item: pick a business from a searchable list, then the same
  ChatSimulator against the admin endpoints. Add "Probar su agente" on each tenant row.
- Map every new error code to Spanish in both apps' api-errors.ts.

TESTS (all must pass)
- Core unit tests with in-memory repos and FakeLlm: thread key format, version pinning,
  StartNewThread, HandleIncomingMessage stores inbound + outbound, no partial turn on LLM
  failure.
- Graph tests with FakeLlm: one question per message; order follows the config; disabled
  questions are skipped; a custom question is asked; cards appear before name/contact is
  requested; over-budget note; tone changes wording but not the sequence of intents.
- Persistence test (the Day 3 checkpoint): run two turns, dispose the engine and build a new
  runtime + checkpointer against the same Postgres, send a third message, and assert the
  state and transcript continue.
- API integration tests: scoping (tenant A never sees tenant B's threads), admin endpoints
  require the admin flag, reset creates a new thread key, 503 and 429 paths, the state panel
  shape, agent_tested flips after the first message.
- Concurrency test: two simultaneous POST /simulator/messages on one thread run one after
  the other (no interleaved state).
- LangSmith tests: the anonymizer masks emails, Argentine phone numbers and DNI-like
  numbers; graph invocation receives the expected run_name, tags and metadata (assert on the
  config passed, no network); a failing tracer does not fail the turn; the run id is stored
  on outbound messages.
- Frontend tests: ChatSimulator rendering and send flow, KnownFactsPanel "Pendiente",
  optimistic bubble + error resend, config_outdated banner, backoffice tenant picker.
- Run everything CI runs: uv run ruff check ., uv run ruff format --check ., uv run pyright,
  uv run alembic upgrade head, uv run --all-packages pytest, schema regeneration + git diff
  check, pnpm lint, pnpm typecheck, pnpm test. Fix failures; do not skip or xfail tests.

CONFIG AND DOCS
- .env.example, README env table and config.py: LLM_MODEL, the provider API key variable,
  LLM_TIMEOUT_SECONDS (default 20), SIMULATOR_DAILY_LIMIT (default 300), and the LangSmith
  variables (LANGSMITH_TRACING, LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_ENDPOINT,
  LANGSMITH_TRACING_SAMPLING_RATE, LANGSMITH_REDACT_PII, LANGSMITH_UI_URL). None of the
  LangSmith variables is required in production. They are runtime env only, never Docker
  build args.
- ARCHITECTURE.md: replace the "When added" Agent paragraph with what now exists (ports,
  runtime, checkpointer migration, transcript vs checkpoint, where the product graph lives,
  the LLM port and why it has two operations, and LangSmith: what is traced, the metadata,
  PII redaction, and how to turn it on).
- README architecture diagram: Conversation, AgentRuntime port, LangGraph runtime, Postgres
  checkpointer and the web chat simulator are no longer planned.
- docs/roadmap-mvp.md: mark Day 3 done (with Part 0) or note what moved.

OUT OF SCOPE
Properties import and the Properties screen, visit proposals and hand-off (Day 4), WhatsApp
(Day 5), the inbox (Day 6), streaming responses.

PROCESS
1. Start with a plan only (use plan mode): Part 0 changes, new tables and migrations
   (including the checkpointer tables), the core ports and use cases, the graph nodes and
   transitions, the API shapes and error codes, the web and backoffice components, the
   package versions you will pin, and any open question. Wait for my OK before editing.
2. Implement Part 0 first, then the backend, then the web and backoffice. Keep everything
   uncommitted (see GIT RULES).
3. Finish with: what changed, the exact commands to run the checks, how I test the "Done
   when" by hand (including the API restart), what you deferred, and the suggested commit
   split with messages. Do not commit.
```
