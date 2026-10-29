# followup-agent-24x7: 12-day MVP roadmap

Goal: a demo-ready MVP of **inmo24x7** by day 7 and of **Cuentas Claras** by day 12,
both running on the shared core and deployed on Oracle Cloud + Supabase.

Every screen element is specified in [`screens-spec.md`](screens-spec.md). Nothing in the
spec is dropped: each screen maps to a day below or to the explicit Post-MVP list.

## Assumptions

- A "day" is one focused work block of about 6–8 hours with a coding agent (OpenCode).
  Working part time, each day is one work session, so the plan takes 3–4 weeks.
- Each day starts with one prompt to OpenCode scoped to that day, and ends with green CI,
  a commit, and a short demo to yourself.
- If a day overruns, cut scope from the "Stretch" items, never from tests or deploy.

## What "MVP" means here

**inmo24x7 MVP**

- A real estate agency signs up alone, sets up its agent with defaults, imports its
  properties, and tries the agent in a web simulator.
- The agent answers on WhatsApp: qualifies the lead, suggests properties from the agency's
  listings, saves contact details, and hands off to a human.
- The agency sees its leads in the panel, confirms visits, and gets notified of each new lead.

**Cuentas Claras MVP**

- A service company signs up with the same onboarding, imports its clients and invoices
  from a CSV, and connects WhatsApp and its own Mercado Pago account.
- Automatic WhatsApp reminders with escalation and a Mercado Pago payment link.
- Payments through Mercado Pago mark invoices as paid automatically.
- The agent answers typical replies; payment promises and installment plans need the owner's
  one-tap approval.
- A dashboard with total owed, payment promises, and money recovered this month.

## Post-MVP

- ARCA integration (reading issued invoices); CSV import covers the MVP and C2 shows only
  the "coming soon" notice.
- Bank statement import and receipt verification with OCR; Day 10 uses the downloaded
  receipt media with manual verification.
- CRM integrations for real estate agencies.
- Charging your own subscription to customers.
- AI-visibility lead magnet.
- Términos and Política de privacidad page content (S1 shows the links in Day 1).
- Planes administration beyond a read-only plan display.
- Conversaciones cross-tenant viewer if it does not fit Day 7 (inmo24x7) or Day 11
  (Cuentas Claras).

## Start on day 1, in parallel: things with lead time

These do not depend on code and some take days. Start them all on day 1.

| Task | Why | Typical lead time |
| --- | --- | --- |
| Meta business verification and Tech Provider setup | Required for Embedded Signup with real customers | Days to weeks |
| Meta test app with a test WhatsApp number | Lets you develop and demo before verification | Minutes |
| WhatsApp utility templates for reminders (Cuentas Claras) | Business-initiated messages need approved templates | Minutes to 1–2 days |
| WhatsApp template for visit confirmation / follow-up outside the 24-hour window (inmo24x7) | Confirming a visit later is outside the customer-service window | Minutes to 1–2 days |
| Mercado Pago OAuth application with the redirect URL on the production domain | Each business connects its own account | Minutes to days |
| Supabase project (São Paulo) with Auth: Google + magic link | Auth and production database | Minutes |
| Oracle Cloud ARM VM (São Paulo if capacity allows) | Production hosting | Minutes to days if capacity is short |
| Domain and DNS for API, panels and landings | Webhooks need a public HTTPS URL | Hours |
| Mercado Pago developer account, test users and credentials | Payment links and payment webhooks | Minutes |
| Source for Argentine holidays (`holidays` package, AR), verified for 2026–2027 | "No enviar en feriados" must be correct | Minutes to verify |
| LLM API key with enough rate limit | Agents and tests | Minutes; higher tiers may need prepaid balance |

---

## Days 1–7: inmo24x7

### Day 1: identity, app shell and sign-up (done)

- **Identity** context in core: verify Supabase JWTs behind a port, profiles with roles
  (owner, manager, agent, viewer) and the global admin flag.
- Tenant scoping on every endpoint; admin endpoints require the admin flag.
- Sign-up creates tenant + owner profile + trial plan in one use case.
- Web app shell: router, auth guard, and the S5 sidebar layout.
- S1 Ingreso: Google and magic link sign-in, with the Términos and Política links.
- Admin-only backoffice shell.

**Screens:** S1, S5 (shell), S8 (admin shell).

**Done when:** you can sign up with Google, land on your own empty panel, and the backoffice
is only reachable with an admin user.

**Follow-up fixes (done with Day 2):** Supabase secrets are no longer baked into the API
image; JWT verification accepts ES256/RS256 with one cached JWKS client and checks the
issuer; production config accepts a JWT secret or a JWKS URL; the web no longer loops when
`/me` fails; self-serve sign-up picks the next free slug.

### Day 2: the onboarding wizard and agent configuration (done)

- Full five-step S2 wizard with progress and "Terminar después" resume.
- Agent configuration stored in Tenancy and versioned.
- Qualification questions are data the graph reads, not hard-coded.
- Setup checklist on S5 reflects onboarding progress.
- Agente screen edits the same configuration after onboarding.
- Configuración screen holds the business profile, hours, and notification destinations.

**Screens:** S2, S5 (checklist), inmo24x7 Agente, inmo24x7 Configuración.

**Done when:** a new account reaches the "try your agent" step in under 3 minutes without
help, and resumes at the same step after leaving.

**Moved or placeholder:** step 3 (Probalo) is a placeholder until the Day 3 simulator, step
4 (WhatsApp) is static until Day 7, and the checklist facts for tested agent, properties,
WhatsApp and Meta verification are providers that return false until their days plug in.
The lead notification email is stored but sent on Day 5.

### Day 3: conversation runtime and the simulator

- **Conversation** context: `AgentRuntime` port, LangGraph implementation, Postgres
  checkpointer with `thread_id = tenant_id:channel:visitor_id`.
- Channel-agnostic flow: incoming message → graph → outgoing messages.
- Fake LLM for deterministic tests.
- S3 simulator with "Lo que el agente ya sabe" exposed from graph state, Reiniciar, and
  seeded sample properties per tenant.
- The same simulator component in the wizard and the S8 backoffice.

**Screens:** S3, S8 (simulator).

**Done when:** you chat with a basic agent in the simulator, restart the API, and the
conversation continues where it was, including the structured state panel.

**Status: done** (together with the Day 2 follow-ups: server-owned question keys, the 409 on
concurrent agent saves, and the S4 step copy).

**Moved or changed:** sample properties are a static fixture behind a `PropertySearch` port
instead of rows seeded per tenant, so Day 4 replaces the adapter rather than migrating seed
data. The basic qualification graph, prompts and the LLM port with its five providers landed
here; Day 4 adds real property search, visit proposals and hand-off on top of them. The
backoffice simulator (S8) shipped with this day, and so did LangSmith tracing of every turn
(PII redacted, "Ver traza" from backoffice messages).

### Day 4: properties and the lead agent

- S7 properties: CSV and XLSX import with per-item validation, downloadable row-level error
  report, manual create/edit, publish/pause, and inquiries per property.
- **Leads** agent driven by the configured qualification questions, with tools to search
  properties, save contact, and propose a visit inside team hours.
- Lead statuses from S5; the graph shows options before asking for personal data, asks one
  question per message, and only uses real property links.
- Prompts as versioned files; test that every declared tool has a handler.

**Screens:** S7, S3 (real search), S5 (statuses).

**Done when:** in the simulator a lead gets matching properties, leaves contact details,
and is handed off, and the lead appears in the panel with its status.

### Day 5: WhatsApp messaging and notifications

- **Messaging** context: webhook verification, HMAC signature check, fast 200 with background
  processing, tenant resolution by `phone_number_id`, deduplication by message id, Argentine
  number normalization, encrypted tokens.
- Sending through Cloud API, with a fake adapter for tests.
- Connect the Meta test number to a test tenant (manual for now).
- New-lead email notification.
- A Meta template for messages outside the 24-hour window (visit confirmation/follow-up).

**Screens:** S2 (email), S5 (active badge and number), S6 (message delivery).

**Done when:** you message the test number from your phone and the agent qualifies you end to
end; the agency receives the new-lead notification.

### Day 6: the inbox and dashboard KPIs

- S6 inbox: full transcript, human takeover (pause the agent per thread and reply through
  WhatsApp), confirm visit, tabs, search, and CSV export.
- System events such as "El agente derivó la consulta a tu equipo".
- S5 KPIs: out-of-hours inquiries, average first-response time, and booked visits.

**Screens:** S6, S5 (KPIs and "Para atender hoy").

**Done when:** a lead handed off on Day 4 is visible in the inbox, a human takes over the
conversation, and confirming a visit updates the status and notifies the lead.

### Day 7: WhatsApp connection, backoffice parity, deploy and demo

- S4 Embedded Signup: token exchange, phone registration, webhook subscription, test message,
  status card, "Pendiente en Meta", and translated Meta errors.
- Connection health: store Meta error codes, detect revoked tokens and failing webhooks.
- S8/S9 backoffice parity: KPIs, filters, detail, audit log from Tenancy, plan usage, users,
  suspend, reconnect link, and manual connection fallback.
- Deploy to Oracle and Supabase; run migrations on deploy; daily `pg_dump` backup.
- Record a 3-minute demo.

**Screens:** S4, S8, S9.

**Done when:** a brand-new account goes from sign-up to a working agent on WhatsApp in
production in under 10 minutes. **inmo24x7 MVP is demo-ready.**

**Stretch:** test link / QR at the end of the wizard; cross-tenant Conversaciones viewer.

---

## Days 8–12: Cuentas Claras

### Day 8: product skeleton, clients and invoices

- `apps/cuentas-claras/{api,web,backoffice}` and `@followup/api-client-cuentas-claras`,
  reusing core, `@followup/ui`, the onboarding wizard, and the simulator.
- **Clientes** screen: the companies that owe money.
- C2 Facturas: CSV template download, CSV import with a report, tabs with counts, search,
  columns, statuses, "Lo próximo", and pagination. ARCA notice only.

**Screens:** C2, Cuentas Claras Clientes.

**Done when:** a service company signs up with the same onboarding and sees its imported
invoices in the panel.

### Day 9: scheduling, reminders and payments

- **Scheduling** context in core: jobs in Postgres and a small worker process.
- C4: editable reminder sequence, send window, Argentine holidays, pause on promise, and
  escalation to the owner.
- Templates per tenant with Meta status sync.
- Mercado Pago OAuth per tenant; payment link per invoice; payment webhook marks the invoice
  paid and cancels pending reminders.

**Screens:** C4.

**Done when:** an invoice due in the test data triggers a reminder on your phone, you pay it
with a Mercado Pago test user, and the invoice turns paid.

### Day 10: the collections agent and approvals

- **Collections** graph that handles replies: "Ya pagué", "Mandame la factura",
  "¿Puedo pagar el 15?".
- C3: promise, installment plan, and payment verification cards.
- Receipt media downloaded from WhatsApp and stored; verify payment against Mercado Pago.
- Counter-offers and "Responder yo", reusing the takeover from Day 6.
- After a decision, the agent continues the conversation.

**Screens:** C3.

**Done when:** you reply "puedo pagar el viernes" to a reminder, approve the promise from the
panel, and the client receives the confirmation.

### Day 11: dashboard, backoffice and deploy

- C1 dashboard: aging buckets, attention list, today's activity, next send time, and the
  Aprobaciones count badge.
- C5 backoffice: failed sends with retry, template health, Mercado Pago webhook health, and
  the tenants table.
- Deploy Cuentas Claras to Oracle; both products share the Supabase database.

**Screens:** C1, C5.

**Done when:** the dashboard reflects imported invoices and reminders, and the backoffice
shows failed sends with a working retry.

### Day 12: hardening, monitoring and launch kit

- Error monitoring and alerts on failed webhooks and failed reminders.
- Full fresh-account test of both products from sign-up, with a stopwatch.
- Landing page per product with the pitch and a sign-up button.
- Pilot kit: demo video for Cuentas Claras, outreach message, list of the first 10 prospects
  per product.

**Done when:** both products run in production, each has a landing page, and you have pilot
conversations scheduled. **Cuentas Claras MVP is demo-ready.**

**Stretch:** ARCA homologation proof of concept (read issued invoices by number).

---

## Checkpoints

| Day | Checkpoint |
| --- | --- |
| 3 | Agent conversation survives an API restart |
| 7 | inmo24x7 demo in production on real WhatsApp |
| 9 | A reminder is sent and a test payment marks the invoice as paid |
| 11 | Cuentas Claras dashboard and backoffice reflect live data |
| 12 | Both products live with landing pages and pilots scheduled |

## Main risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Tech Provider verification not approved in time | Manual number connection from the backoffice; same customer flow later |
| WhatsApp templates rejected | Rewrite as neutral utility text and resubmit early (day 1, not day 9) |
| Mercado Pago OAuth redirect not approved | Manual per-tenant credentials through the backoffice during the pilot |
| Argentine holidays source incomplete for 2026–2027 | Ship a manual holiday list and swap in the package when verified |
| Oracle ARM capacity unavailable | Google Cloud Run for the API, same Supabase database |
| LLM rate limits during tests | Fake LLM in tests; real model only in manual demos |
| A day overruns | Move its stretch items to the backlog; keep tests and deploy |

## Screen coverage

| Day | Screens covered |
| --- | --- |
| 1 | S1, S5 (shell), S8 (admin shell) |
| 2 | S2, S5 (checklist), inmo24x7 Agente, inmo24x7 Configuración |
| 3 | S3, S8 (simulator) |
| 4 | S7, S3 (real search), S5 (statuses) |
| 5 | S2 (email), S5 (active badge), S6 (delivery) |
| 6 | S6, S5 (KPIs and inbox) |
| 7 | S4, S8, S9 |
| 8 | C2, Cuentas Claras Clientes |
| 9 | C4 |
| 10 | C3 |
| 11 | C1, C5 |
| 12 | launch and hardening across both products |

Nav-only screens: Simulador (Day 3/8), Conversaciones (Day 7 or Post-MVP), Plantillas de
WhatsApp (Day 9), Salud del sistema (Day 7), Planes (read-only Day 7/11; Post-MVP beyond).

## Daily routine

1. Write the day's OpenCode prompt from this file (one section per prompt).
2. Ask for the plan first and confirm it.
3. Review the diff, run the app, and try the "Done when" check yourself.
4. Commit with green CI and update this file with what moved.
