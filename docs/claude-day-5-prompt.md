# Claude Code prompt — Day 5: WhatsApp messaging and new-lead email

Create the branch yourself first (`git checkout -b feature/day-5`), open Claude Code at the
repo root, and paste everything inside the block. Claude will not commit anything.

```text
You are working in the followup-agent-24x7 monorepo on Day 5 of docs/roadmap-mvp.md.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- You MAY run read-only git commands (git status, git diff, git log).
- Leave every change uncommitted in the working tree. I review the diff and commit myself.
- At the end, give me a suggested commit split (files per commit + message), but do not run it.

READ BEFORE PLANNING
README.md (Local development), ARCHITECTURE.md, docs/roadmap-mvp.md (Days 5–9),
docs/screens-spec.md (S2, S4, S5, S6, S9). Then the code this day builds on:
packages/core/src/followup_core/conversation (application/threads.py: HandleIncomingMessage,
TurnObserver; domain/thread.py: Channel, ThreadKey), apps/inmo24x7/api/src/inmo24x7_api/
{container,main,config,simulator,tracing}.py, leads/ (graph.py, tools.py, display.py,
application/record_turn.py, domain/contact.py, domain/slots.py), scripts/dev.py,
scripts/seed_dev.py, docker-compose.yml, .env.example, apps/inmo24x7/web/src (Inicio,
Consultas, onboarding step 4) and apps/inmo24x7/backoffice/src.

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, the domain imports nothing outward,
container.py is the composition root, errors are stable codes {"code": "..."} mapped to
Spanish in the frontends, generated OpenAPI client (regenerate schema.ts), shared
presentational components in @followup/ui, Alembic migrations only. Code and docs in
English; UI copy, emails and agent replies in Spanish (Argentina, voseo). Never log message
text, phone numbers or emails (personal data); log ids, codes and timings.

=====================================================================
PART 0 — Day 4 follow-ups
=====================================================================
0.1 Backoffice "Solo administradores de la plataforma." screen: show the signed-in email and
    a "Cerrar sesión" button. When /me fails (401, 404 profile_not_found, network), show a
    Spanish error card with "Reintentar" and "Cerrar sesión" instead of the admin message.
    Tests for the three cases.
0.2 Visit slots: propose_slots returns two consecutive half hours (e.g. 10:30 and 11:00),
    which is not a real choice. Return the first free slot and the first slot at least 3
    hours later or on another day, still inside team hours (S6 shows "el sábado 10:30 o el
    lunes 18 h"). Update the slot tests.
0.3 A lead who picks another slot or another property after a visit was proposed: replace
    the proposed visit (cancel the old one, record the new one) instead of ignoring it.
    Test it.

=====================================================================
PART 1 — Day 5 goal
=====================================================================
Done when:
A) With no Meta account at all: `scripts/simulate_whatsapp.py "Hola, busco un 2 ambientes
   en Palermo"` posts a correctly signed webhook to the local API; the agent answers through
   the log sender; the conversation, the lead and the delivery statuses show in Consultas;
   the new-lead email arrives in the local Mailpit inbox.
B) With the Meta test number connected from the backoffice and a tunnel to my machine: I
   message the test number from my phone, the agent qualifies me end to end (text, property
   messages with links, visit slots as WhatsApp reply buttons, hand-off), and the agency's
   notification email arrives in Mailpit.

BACKGROUND JOBS (core, first piece of the Scheduling context from Day 9, built now)
The webhook must answer Meta in milliseconds, and in-process background tasks are lost on a
restart. Build the minimal Postgres job queue now; Day 9 extends it, not replaces it.
- packages/core/src/followup_core/scheduling: jobs table (id, kind, payload JSONB, run_at,
  status queued|running|done|failed|dead, attempts, max_attempts, locked_until, last_error
  code, dedupe_key unique nullable, created_at, finished_at). Enqueue inside the caller's
  transaction. Claim with SELECT ... FOR UPDATE SKIP LOCKED; exponential backoff with
  jitter; a job exceeding max_attempts goes to dead and is logged as an error; a stuck job
  (locked_until passed) is reclaimed.
- A worker process: `uv --directory apps/inmo24x7/api run python -m inmo24x7_api.worker`,
  with a handler registry (each job kind has exactly one handler; test it like the tool
  registry), graceful shutdown on SIGTERM, and a concurrency setting. scripts/dev.py starts
  it next to the API. The API Docker image can run it with a different command; document it.

MESSAGING CONTEXT (core, packages/core/src/followup_core/messaging)
- WhatsAppConnection per tenant: tenant_id (unique), phone_number_id (unique), waba_id,
  display_phone_number, verified_name, encrypted access token, status
  connected|disconnected|error, last_error_code, last_inbound_at, connected_at, updated_at.
- Token encryption: AES-GCM (the cryptography package), key from TOKEN_ENCRYPTION_KEY
  (base64, 32 bytes), ciphertext stored with a key id prefix so keys can be rotated later.
  The token is never returned by any endpoint or logged.
- Phone numbers: normalize with the phonenumbers package. Store E.164 (+5491155550188),
  display as "+54 9 11 5555-0188", and always send replies to the wa_id exactly as Meta
  sent it. Tests with the Argentine formats (with and without 9 and 15, with and without
  +54).
- Inbound webhook, in the product API:
  - GET /webhooks/whatsapp: hub.mode=subscribe + hub.verify_token == WHATSAPP_VERIFY_TOKEN
    → return hub.challenge as text/plain; otherwise 403.
  - POST /webhooks/whatsapp: read the RAW body and verify X-Hub-Signature-256 (HMAC-SHA256
    with META_APP_SECRET, constant-time compare) before parsing; invalid or missing → 401
    and a log line. Then for every message: resolve the tenant by phone_number_id, insert an
    inbound event row (wamid unique → duplicates are dropped by the database, not by code),
    enqueue a job, and return 200. Unknown phone_number_id → store as ignored, log a
    warning, still 200. Status updates (sent, delivered, read, failed) update the delivery
    status and error code of our outbound message by wamid. Never call the LLM or Meta inside
    the webhook request.
  - The raw payload contains personal data: a purge job deletes payloads older than 30
    days (keep the row ids and statuses).
- Processing inbound messages (job handler):
  - Debounce: the job runs INBOUND_DEBOUNCE_SECONDS (default 3) after the message arrives.
    The handler takes ALL pending inbound events of that thread in timestamp order under the
    existing per-thread advisory lock and runs ONE agent turn with their texts joined, so a
    burst like "hola" / "busco depto" / "en palermo" gets one answer, in order.
  - ThreadKey = tenant_id:whatsapp:<wa_id>. It reuses HandleIncomingMessage, so leads are
    created by RecordLeadTurn exactly as in the simulator, with is_test=false.
  - Interactive replies: a button reply carrying a slot id becomes the same slot selection
    the simulator sends. Make one shared function for both channels.
  - Non-text messages (audio, image, video, document, sticker, location, contacts) are
    stored with their type and get a fixed reply without calling the LLM: "Por ahora solo
    puedo leer mensajes de texto. ¿Me lo escribís?". Reactions are ignored.
  - Mark processed inbound messages as read in WhatsApp.
- Contact from the channel: on WhatsApp the visitor's phone is already known. Fill the
  lead's contact from the normalized number when the thread starts, so the agent never asks
  for a phone on WhatsApp (it may still ask for the name). Graph test for this.
- Sending (job handler, so a Meta outage never rolls back a turn):
  - After a turn, outbound messages are stored with delivery_status=queued and ONE send job
    per turn sends them in order.
  - Rendering per payload type: text → text message (split above 4,096 chars); property
    cards → one text message each with the title in bold, address, formatted price, the
    over-budget note and the listing link (preview_url on); visit slots → an interactive
    reply-buttons message (max 3 buttons, titles max 20 chars, e.g. "jue 6/11 10:30", ids =
    slot ids); system messages (hand-off event) are never sent to the lead.
  - Retries with backoff on 429 and 5xx; permanent errors mark the message failed with the
    Meta error code (Day 7 translates codes for humans).
  - 24-hour customer service window: free-form messages are only sent if the thread's last
    inbound message is less than 24 hours old; otherwise the sender refuses with
    "outside_service_window". Add send_template(name, language, parameters) for messages
    outside the window. The visit-confirmation template name and language are stored per
    connection (WHATSAPP_DEFAULT_TEMPLATE / _LANGUAGE as defaults). Day 6 uses it to confirm
    visits; today only the backoffice test uses it.
  - Senders behind a WhatsAppSender port: CloudApiSender (Graph API base URL and version
    from config; check the current Graph API version before choosing the default), a
    LogSender for local development without Meta (stores a fake wamid and simulates sent →
    delivered → read status updates), and a recording fake for tests. WHATSAPP_SENDER =
    cloud | log, default log in .env.example.
- Simulator script scripts/simulate_whatsapp.py: builds a realistic Cloud API webhook payload
  (text, a button reply with --slot, or an audio with --audio), signs it with
  META_APP_SECRET and posts it to the local API, for a phone number passed with --from.
  Use it in the README and in the end-to-end test.

CONNECTING A NUMBER (manual today; Day 7 adds Embedded Signup)
- Backoffice, per business (a "WhatsApp" section reachable from the business row; Day 7
  turns it into S9): form with phone_number_id, waba_id, display number and access token;
  "Probar conexión" (reads the phone number from the Graph API and stores
  display_phone_number and verified_name), "Suscribir la app" (subscribes the app to the
  WABA's webhooks), "Enviar mensaje de prueba" (sends the template to a number I type; Meta
  test numbers come with the "hello_world" en_US template), "Desconectar". A status card with
  Conectado / Desconectado / Error, the last error code and the last message received.
- Admin endpoints under /admin/tenants/{tenant_id}/whatsapp (require_platform_admin).
  Errors: whatsapp_connection_invalid, whatsapp_phone_number_taken, whatsapp_api_error
  (include the Meta error code in the body for admins only).
- Plug in the whatsapp_connected setup fact provider.

NEW-LEAD EMAIL (S2 "Avisarme de cada lead en")
- EmailSender port with an SMTP adapter (SMTP_HOST, SMTP_PORT, SMTP_USERNAME,
  SMTP_PASSWORD, SMTP_STARTTLS, EMAIL_FROM) and a fake for tests. Add a Mailpit service to
  docker-compose.yml for development (SMTP 1025, web UI 8025) and point .env.example at it.
- Only for real leads (never simulator tests), sent as jobs with a dedupe key per lead and
  kind, to the tenant's notification emails:
  - when the lead is handed off (visit_proposed or human_requested): subject "Nueva
    consulta: {name or phone} · {one-line summary}", body with the answers, the proposed
    visit (day, time, property) or "Pidió hablar con alguien", and a button/link to
    {PANEL_URL}/consultas?lead={id};
  - if 15 minutes after the first message there is still no hand-off: one "Consulta en
    curso" email with what is known so far.
  Plain text and simple HTML, Spanish copy. Each lead gets at most one email of each kind.

PANEL (web)
- Inicio (S5): "Agente activo" badge with the WhatsApp number when connected (S5 header);
  the checklist item flips. Hide the badge when not connected.
- Consultas: WhatsApp leads appear like simulator ones but without the "Prueba" badge, with
  the channel shown ("por WhatsApp"). Outbound messages in the transcript show a small
  delivery status (Enviado, Entregado, Leído, No se pudo enviar). Non-text inbound messages
  show their type ("Audio", "Imagen").
- Wizard step 4: if a connection exists, show the S4 status card (Cuenta de Meta, Número,
  Recepción de mensajes, Mensaje de prueba) from the connection; otherwise keep today's
  placeholder.

CONFIG AND DOCS
- New settings: META_APP_SECRET, WHATSAPP_VERIFY_TOKEN, META_GRAPH_BASE_URL,
  META_GRAPH_API_VERSION, WHATSAPP_SENDER, WHATSAPP_DEFAULT_TEMPLATE,
  WHATSAPP_DEFAULT_TEMPLATE_LANGUAGE, TOKEN_ENCRYPTION_KEY, INBOUND_DEBOUNCE_SECONDS,
  WORKER_CONCURRENCY, SMTP_*, EMAIL_FROM, PANEL_URL. Production requires META_APP_SECRET,
  WHATSAPP_VERIFY_TOKEN, TOKEN_ENCRYPTION_KEY (valid 32-byte key), WHATSAPP_SENDER=cloud,
  SMTP_HOST, EMAIL_FROM and PANEL_URL. Runtime env only, never Docker build args. Add a
  one-liner to generate TOKEN_ENCRYPTION_KEY to the README.
- README: "Testing WhatsApp locally" with both paths: (A) the simulate script + log sender +
  Mailpit; (B) the Meta test number: create the test app, add my phone as a test recipient,
  create a long-lived system user token (permissions whatsapp_business_messaging and
  whatsapp_business_management) instead of the 24-hour temporary token, run a tunnel
  (cloudflared or ngrok) to port 8001, set the callback URL and verify token in the app's
  WhatsApp configuration, subscribe the "messages" field, connect the number in the
  backoffice, set WHATSAPP_SENDER=cloud.
- ARCHITECTURE.md: Messaging and Scheduling contexts, the webhook → event → job → turn →
  send pipeline, debounce and ordering, the 24-hour window, why sending is a job.
- README architecture diagram: WhatsApp and Messaging are no longer planned; add the worker.
- docs/roadmap-mvp.md: mark Day 5 done (with Part 0) and note that the job queue moved
  forward from Day 9.
- Seed: give "Inmobiliaria Sur" a fake WhatsApp connection (phone_number_id "dev-phone-1",
  log sender) so path A works right after `scripts/dev.py --seed`.

TESTS (all must pass; the Graph API is mocked at the HTTP level, never called for real)
- Webhook: verify challenge ok and wrong token; signature valid, invalid, missing, and
  computed over the raw body; duplicate wamid processed once; unknown phone_number_id;
  status updates change delivery status; the request never calls the LLM or Meta.
- Jobs: claim with SKIP LOCKED (two workers never run the same job), retries and backoff,
  dead after max attempts, reclaim stuck jobs, dedupe keys, handler registry completeness.
- Processing: debounce joins a burst into one turn in order; per-thread ordering; button
  reply → slot selection; non-text fixed reply; contact prefilled, so the agent never asks
  for a phone on WhatsApp; leads from WhatsApp have is_test=false.
- Sending: rendering of text, cards and slot buttons (limits); retry on 429/5xx; permanent
  failure stored with its code; 24-hour window refusal; template send.
- Encryption round trip, wrong key, key id prefix. Phone normalization cases.
- Email: one hand-off email per lead; the 15-minute email only without hand-off; never for
  simulator leads; recipients are the tenant's notification emails.
- Backoffice endpoints: admin only, token never returned, test connection and subscribe call
  the mocked Graph API.
- End to end with the log sender and the fake LLM: the simulate script's payload → worker →
  agent → outbound delivered → lead in /leads → email in the fake sender.
- Frontend: Agente activo badge, delivery labels in Consultas, wizard step 4 status card,
  backoffice connection form and status card, 0.1 admin screen states.
- Run everything CI runs: uv run ruff check ., uv run ruff format --check ., uv run pyright,
  uv run alembic upgrade head, uv run --all-packages pytest, schema regeneration + git diff
  check, pnpm lint, pnpm typecheck, pnpm test. Fix failures; do not skip or xfail tests.
- Then run path A yourself (dev.py --seed, simulate script, Consultas, Mailpit) and report
  what you saw.

OUT OF SCOPE
Embedded Signup and translated Meta errors (Day 7), takeover and visit confirmation (Day 6),
WhatsApp notifications to the agency (stretch), downloading media (Day 10), template
management UI, typing indicators.

PROCESS
1. Plan first (use plan mode): Part 0, the tables and migrations (core vs product), the job
   queue and worker, the webhook → job → turn → send flow with debounce and ordering, the
   payload rendering, the email triggers, config, the backoffice and panel changes, the
   packages you will add with pinned versions, and open questions. Wait for my OK.
2. Implement Part 0, then jobs, then messaging and the webhook, then sending, then email,
   then the UI.
3. Finish with what changed, exact commands for paths A and B, what you deferred, and the
   suggested commit split. Do not commit.
```
