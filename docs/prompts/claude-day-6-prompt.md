# Claude Code prompt — Day 6: the inbox (takeover, confirm visit) and dashboard KPIs

Create the branch yourself first (`git checkout -b feature/day-6`), open Claude Code at the
repo root, and paste everything inside the block. Claude will not commit anything.

```text
You are working in the followup-agent-24x7 monorepo on Day 6 of docs/roadmap-mvp.md.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- You MAY run read-only git commands (git status, git diff, git log).
- Leave every change uncommitted in the working tree. I review the diff and commit myself.
- At the end, give me a suggested commit split (files per commit + message), but do not run it.

READ BEFORE PLANNING
README.md, ARCHITECTURE.md, docs/roadmap-mvp.md (Days 4–7), docs/screens-spec.md (S5, S6).
Then the code this day builds on: packages/core/src/followup_core/conversation
(application/threads.py HandleIncomingMessage, domain/thread.py Thread/Message/Author,
simulator), packages/core/src/followup_core/messaging (application/pipeline.py: processing,
sending, within_service_window, send_template), packages/core/src/followup_core/scheduling,
apps/inmo24x7/api/src/inmo24x7_api/leads (domain/lead.py, application/record_turn.py,
application/notify.py, router.py, display.py, graph.py), worker.py, container.py,
scripts/seed_dev.py, scripts/simulate_whatsapp.py, and apps/inmo24x7/web/src (pages/
consultas.tsx, pages/inicio.tsx, components/SetupChecklist.tsx).

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, the domain imports nothing outward,
container.py is the composition root, errors are stable codes {"code": "..."} mapped to
Spanish in the frontends, generated OpenAPI client (regenerate schema.ts), shared
presentational components in @followup/ui, Alembic migrations only. Code and docs in
English; UI copy and messages to leads in Spanish (Argentina, voseo). Never log message
text, phone numbers or emails. Every tenant endpoint takes the tenant from the profile.

=====================================================================
PART 0 — Migration heads guard
=====================================================================
Every new core revision after the product chain exists creates a second Alembic head (Day 5
needed inmo_0003 to merge them). Make it impossible to forget:
- A test that loads the root alembic.ini and asserts there is exactly one head.
- Document the rule in ARCHITECTURE.md ("Migrations"): core revisions chain to the core
  head; after adding one, add a product merge revision (empty upgrade) whose down_revision
  is (current product head, new core head). If today's work adds core revisions, add the
  merge revision too.

=====================================================================
PART 1 — Day 6 goal
=====================================================================
Done when (path A, no Meta account): I simulate a WhatsApp lead with
scripts/simulate_whatsapp.py until it picks a visit slot and is handed off. It shows in
Consultas under "Para atender". I click "Tomar la conversación", write a reply in the panel
and the lead receives it (log sender); the lead answers with the simulate script and the
agent does NOT answer. I click "Confirmar visita": the lead receives the confirmation, the
status turns "Visita confirmada", a system event appears in the transcript, and the lead
leaves "Para atender". Inicio shows this week's KPIs and "Para atender hoy" with real data.
Path B is the same from my phone with the Meta test number.

TAKEOVER (core Conversation + product Leads)
- Thread control: add control = agent | human, controlled_by_profile_id, control_changed_at
  to threads (migration). Domain methods take_over(profile, at) and release(profile, at),
  each appending a system message to the transcript: "{nombre} tomó la conversación" /
  "{nombre} devolvió la conversación al agente". Use the profile display name (fall back to
  the email).
- While control = human, HandleIncomingMessage (both channels, and the WhatsApp debounced
  job) stores inbound messages but never calls the runtime and never sends an agent reply.
  Check the control flag under the existing per-thread advisory lock, so a takeover racing
  a turn is safe: a turn already running finishes, any later one is skipped. Test the race.
- Human replies: POST /leads/{id}/messages {text 1–4096} → stores an outbound message with
  author human and the profile id, then:
  - WhatsApp: enqueue the existing send job; outside the 24-hour window refuse with 409
    "outside_service_window" (nothing stored).
  - Simulator: no sending; the message appears in the simulator transcript (so I can test
    takeover without WhatsApp).
  Only allowed while the thread is under human control (409 "conversation_not_taken").
- Release: "Devolver al agente". When the agent resumes, the LLM context it builds from the
  recent transcript must include the team's messages (labelled as the team), so it does not
  repeat questions the human already answered. Test it with the FakeLlm.
- Endpoints: POST /leads/{id}/takeover, POST /leads/{id}/release. Taking over a conversation
  another person controls is allowed and moves control to the caller (the UI asks first).
- Roles: owner, manager and agent can take over, reply, release and confirm visits; viewer
  is read-only (403 "forbidden").

CONFIRM VISIT
- POST /leads/{id}/visits/{visit_id}/confirm {starts_at?}: optionally change the time (must
  be in the future), set the visit confirmed, the lead status visit_confirmed (domain
  transition), append the system event "{nombre} confirmó la visita", and notify the lead:
  - inside the 24-hour window: free text, e.g. "¡Listo, {nombre}! Te confirmamos la visita a
    {dirección} el {sábado 7/11} a las {10:30}. Cualquier cosa, escribinos por acá.";
  - outside the window: the connection's visit-confirmation template with parameters (name,
    address, date and time). If no template is configured → 409 "template_not_configured"
    and nothing changes. Document in the README the exact template I must create and get
    approved in Meta (name, language es_AR, category utility, body with 3 parameters,
    example values), and store its name per connection as on Day 5;
  - simulator leads: the confirmation appears in the simulator transcript, nothing is sent.
  Confirming twice is idempotent. The whole operation is one transaction plus the send job.
- POST /leads/{id}/visits/{visit_id}/cancel with an optional message to the lead (same
  window/template rules for the message; the template is optional here: without a window and
  without a message, just cancel). Status goes back to human_requested so the team follows up.

INBOX API
- "Needs attention" is defined once in the domain: status visit_proposed or human_requested,
  and no human reply after the hand-off; visit_confirmed never needs attention.
- GET /leads?tab=attention|visits|all&q=&include_test=&page=: counts per tab in the response;
  search q matches name, phone (digits only, any format) and zone/answers, accent-insensitive;
  "visits" = leads with a proposed or confirmed visit, ordered by visit time; "attention"
  ordered by urgency (human_requested first, then the soonest proposed visit, then age);
  "all" by last activity. Page size 25.
- GET /leads/{id}: everything the detail pane needs: name, phone (display format), channel,
  status, control state and who controls it, within_service_window and its expiry time,
  answers as display rows for the CONFIGURED questions in config order (custom ones too;
  S6's "Garantía" is a custom question), visits, transcript with author, delivery status and
  system events, and the trace link for admins as today.
- GET /leads/export.csv with the same filters as the list: UTF-8 with BOM and ";" as
  separator (Excel in es-AR opens it correctly); columns: fecha de alta, nombre, teléfono,
  canal, estado, one column per configured question (label as header), visita (fecha y
  propiedad), estado de la visita, última actividad. Max 5,000 rows, test leads excluded
  unless include_test. Do not trace or log the rows.

DASHBOARD KPIs (S5)
- GET /dashboard → this week (Monday 00:00 in the tenant timezone until now), real leads only
  (never is_test):
  - consultas recibidas: leads created; plus "N fuera de horario": leads whose first inbound
    message was outside team hours (is_within_team_hours);
  - calificadas "Con zona y presupuesto": leads with the operation, zone and budget answered
    (only the ones enabled in the config);
  - visitas agendadas "El número que importa": visits proposed or confirmed this week, not
    cancelled, with the confirmed count;
  - respuesta promedio "A cualquier hora": the average, over inbound bursts this week, of the
    time from the first inbound message of the burst to the first agent reply sent for it
    (use the sent timestamp from delivery status when available, otherwise created_at);
    formatted on the client ("6 s", "1 min 20 s"); null when there is no data;
  - para atender hoy: the top 5 leads by the attention ordering, then the most recent leads
    still qualifying, each with name or phone, the one-line summary, status and age.
  Add the database indexes these queries need and keep the endpoint under ~100 ms on the
  seeded data.
- The KPI definitions live in one tested module, with fixed clocks and timezones in tests
  (including a week that crosses midnight in Buenos Aires vs UTC).

WEB
- Consultas (S6), replacing the Day 4 list:
  - Tabs "Para atender · N", "Visitas", "Todas"; search "Buscar por nombre, zona o teléfono";
    "Exportar CSV" (downloads with the current tab, search and test toggle); the "Prueba"
    toggle stays.
  - List items: name or phone, age ("12 min", "1 h", "Ayer"), the one-line summary and the
    status badge.
  - Detail pane: name, phone "· por WhatsApp" or "· simulador"; buttons "Tomar la
    conversación" / "Devolver al agente" and "Confirmar visita"; a visit card ("Visita
    propuesta · Gorriti 4800 · sábado 10:30 · espera tu confirmación", or "Visita confirmada")
    with a confirm dialog that allows changing day and time, and "Cancelar visita"; the
    answers grid; the transcript with bubbles for lead, agent and team (team bubbles show who
    wrote them), centered system events, and delivery labels.
  - Composer at the bottom: enabled only when I control the conversation; otherwise a hint
    "Tomá la conversación para responder". When outside the 24-hour window, the composer is
    disabled with "Pasaron más de 24 horas desde el último mensaje: WhatsApp solo permite
    responder con una plantilla. Podés confirmar la visita igual." Show the window expiry
    ("Podés responder hasta las 18:40").
  - The URL keeps the selected lead (?lead=id) so the new-lead email link opens it, and the
    tab and search, so reload keeps the view.
  - Refresh by polling: the open detail every 5 s and the list every 15 s while the tab is
    visible (no websockets today). New messages appear without losing the composer text.
  - Viewers see everything read-only.
  - Empty states in Spanish for each tab.
- Inicio (S5): header "Hola, {negocio}" / "Esto pasó esta semana con tu agente." and
  "Probar el agente"; the checklist card stays while incomplete; four KPI cards with their
  subtitles; "Para atender hoy" table (Interesado, Busca, Estado, Hace) with "Ver todas" to
  the Consultas attention tab; rows open the lead. An empty state when there is no data yet
  ("Todavía no hay consultas esta semana. Probá tu agente o conectá WhatsApp.").
- Shared pieces (status badge, KPI card, chat transcript bubbles) go to @followup/ui if
  Cuentas Claras will reuse them.

SEED
Extend scripts/seed_dev.py so the inbox and KPIs have data right after `--reset`: about 8
WhatsApp leads for Inmobiliaria Sur spread over this week and last week (some out of hours,
one human_requested, two visit_proposed, one visit_confirmed, some still qualifying, one
with a message older than 24 hours), created by running the real pipeline (simulated
webhooks, worker handlers, FakeLlm, log sender) with an injected clock, not by raw inserts.
Keep the seed idempotent.

TESTS (all must pass)
- Domain: take_over/release with system events; needs-attention rule; confirm and cancel
  transitions; idempotent confirm.
- Takeover: no agent reply on either channel while taken (including a debounced WhatsApp job
  that was queued before the takeover); the race with a running turn; release resumes with
  the team's messages in the LLM context.
- Human reply: WhatsApp send job enqueued; 409 outside the window; 409 when not taken;
  simulator transcript shows it; roles.
- Confirm visit: inside the window sends text; outside sends the template with the right
  parameters; template_not_configured leaves everything unchanged; simulator path; changing
  the time; cancel.
- Inbox API: tab counts and ordering, search by name, zone, phone in different formats,
  scoping (tenant A never sees B), export CSV (BOM, ";", headers from the configured
  questions, test leads excluded, row limit).
- KPIs: each definition with fixed clocks, timezone week boundary, test leads excluded, null
  response time without data.
- Migration single-head test (Part 0).
- Frontend: tabs and counts, search, list → detail via ?lead, takeover button states,
  composer enabled/disabled/outside-window, confirm dialog with time change, cancel, polling
  keeps composer text, viewer read-only, Inicio KPI cards and table, empty states.
- Run everything CI runs: uv run ruff check ., uv run ruff format --check ., uv run pyright,
  uv run alembic upgrade head, uv run --all-packages pytest, schema regeneration + git diff
  check, pnpm lint, pnpm typecheck, pnpm test. Fix failures; do not skip or xfail tests.
- Then run the Done-when path A yourself (dev.py --seed, simulate script, panel) and report
  what you saw.

DOCS
- ARCHITECTURE.md: takeover (control flag, lock, system events), the needs-attention rule,
  KPI definitions, the migration heads rule.
- README: how to test takeover and visit confirmation with path A and path B, and the Meta
  template to create.
- docs/roadmap-mvp.md: mark Day 6 done (with Part 0) or note what moved.

OUT OF SCOPE
Embedded Signup, connection health, backoffice parity and deploy (Day 7); websockets or
push notifications; assigning leads to specific team members; WhatsApp notifications to the
agency; CSV export of transcripts.

PROCESS
1. Plan first (use plan mode): Part 0, the migrations, the control flag and where it is
   checked, the endpoints with shapes and error codes, the KPI queries and indexes, the
   web components and polling, the seed changes, and open questions. Wait for my OK.
2. Implement Part 0, then takeover, then confirm/cancel, then the inbox API and export, then
   KPIs, then the web, then the seed.
3. Finish with what changed, exact commands for the Done-when (paths A and B), what you
   deferred, and the suggested commit split. Do not commit.
```
