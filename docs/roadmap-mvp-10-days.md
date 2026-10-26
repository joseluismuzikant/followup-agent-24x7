# followup-agent-24x7: 10-day MVP roadmap

Goal: a demo-ready MVP of **inmo24x7** by day 6 and of **Cuentas Claras** by day 10,
both running on the shared core and deployed on Oracle Cloud + Supabase.

## Assumptions

- A "day" is one focused work block of about 6–8 hours with a coding agent (OpenCode).
  Working part time, each day is one work session, so the plan takes 3–4 weeks.
- Each day starts with one prompt to OpenCode scoped to that day, and ends with
  green CI, a commit and a short demo to yourself.
- If a day overruns, cut scope from the "Stretch" items, never from tests or deploy.

## What "MVP" means here

**inmo24x7 MVP**
- A real estate agency signs up alone, sets up its agent with defaults, imports its
  properties and tries the agent in a web simulator.
- The agent answers on WhatsApp: qualifies the lead, suggests properties from the
  agency's listings, saves contact details and hands off to a human.
- The agency sees its leads in the panel and gets notified of each new lead.

**Cuentas Claras MVP**
- A service company signs up with the same onboarding, imports its clients and
  invoices from a CSV, and connects WhatsApp.
- Automatic WhatsApp reminders with escalation and a Mercado Pago payment link.
- Payments through Mercado Pago mark invoices as paid automatically.
- The agent answers typical replies, and payment promises need the owner's one-tap approval.
- A dashboard with total owed, payment promises and money recovered this month.

**Out of the MVP (next iteration)**
- ARCA integration (reading issued invoices); CSV import covers the MVP.
- Bank statement import and receipt verification with OCR.
- CRM integrations for real estate agencies.
- Charging your own subscription to customers.
- AI-visibility lead magnet.

## Start on day 1, in parallel: things with lead time

These do not depend on code and some take days. Start them all on day 1.

| Task | Why | Typical lead time |
| --- | --- | --- |
| Meta business verification and Tech Provider setup | Required for Embedded Signup with real customers | Days to weeks |
| Meta test app with a test WhatsApp number | Lets you develop and demo before verification | Minutes |
| WhatsApp utility templates for reminders (Cuentas Claras) | Business-initiated messages need approved templates | Minutes to 1–2 days |
| Supabase project (São Paulo) with Auth: Google + magic link | Auth and production database | Minutes |
| Oracle Cloud ARM VM (São Paulo if capacity allows) | Production hosting | Minutes to days if capacity is short |
| Domain and DNS for API, panels and landings | Webhooks need a public HTTPS URL | Hours |
| Mercado Pago developer account, test users and credentials | Payment links and payment webhooks | Minutes |
| LLM API key with enough rate limit | Agents and tests | Minutes; higher tiers may need prepaid balance |

---

## Days 1–6: inmo24x7

### Day 1: identity, tenant scoping and review fixes
- Apply the pending review fixes (CI branch, single Alembic config, migrations in
  production, `VITE_API_URL`, migration-based test fixture, Node engine, diagram).
- **Identity** context in core: verify Supabase JWTs behind a port, profiles with
  roles (owner, manager, agent, viewer) and the global admin flag.
- Every tenant endpoint scoped by the caller's tenant; admin endpoints require the admin flag.
- Sign-up creates tenant + owner profile + trial plan in a single use case.

**Done when:** you can sign up with Google, land on your own empty panel, and the
backoffice is only reachable with an admin user.

### Day 2: self-serve onboarding wizard
- Wizard in `web`, one decision per screen, with progress and resume:
  business name and type → agent setup with pre-filled defaults (tone, hours,
  qualification questions).
- Onboarding progress stored in Tenancy; setup checklist on the dashboard.
- Notification channels: email destination for new leads (WhatsApp later).

**Done when:** a new account reaches the "try your agent" step in under 3 minutes
without help.

### Day 3: conversation runtime and web simulator
- **Conversation** context in core: `AgentRuntime` port, LangGraph implementation,
  Postgres checkpointer with `thread_id = tenant_id:channel:visitor_id`.
- Channel-agnostic flow: incoming message → graph → outgoing messages.
- Shared chat simulator component in `@followup/ui`, used in the wizard and backoffice.
- A fake LLM for deterministic tests.

**Done when:** you chat with a basic agent in the simulator, restart the API,
and the conversation continues where it was.

### Day 4: the inmo24x7 agent
- **Properties**: CSV/JSON import with per-item validation and an error report;
  search by operation, area and budget.
- **Leads**: qualification graph with structured state (operation, area, budget,
  financing, name, contact) and three tools: search properties, save contact,
  hand off to a human.
- Rules enforced by the graph: show options before asking for personal data,
  one question per message, only real property links.
- Prompts as versioned files; test that every declared tool has a handler.

**Done when:** in the simulator, a lead gets matching properties, leaves contact
details and is handed off, and the lead appears in the panel.

### Day 5: WhatsApp messaging
- **Messaging** context in core: webhook verification, HMAC signature check,
  fast 200 with background processing, tenant resolution by `phone_number_id`,
  deduplication by message id, Argentine number normalization, encrypted tokens.
- Sending through Cloud API, with a fake adapter for tests.
- Connect your Meta test number to a test tenant.
- New-lead notification by email (and WhatsApp to the agency, if time allows).

**Done when:** you message the test number from your phone and the agent
qualifies you end to end; the agency gets the new-lead notification.

### Day 6: WhatsApp connection flow, deploy and demo
- "Conectar WhatsApp" with Embedded Signup: token exchange, phone registration,
  webhook subscription and a test message, with connection status in the panel and
  Meta errors translated to clear Spanish.
- If Tech Provider verification is not approved yet: a backoffice fallback where you
  connect a customer's number manually. The customer flow stays the same later.
- Deploy to Oracle (API, web, backoffice) and Supabase; run migrations on deploy;
  daily `pg_dump` backup to object storage.
- Record a 3-minute demo video.

**Done when:** a brand-new account goes from sign-up to a working agent on WhatsApp
in production in under 10 minutes. **inmo24x7 MVP is demo-ready.**

**Stretch:** test link / QR at the end of the wizard; lead export to CSV.

---

## Days 7–10: Cuentas Claras

### Day 7: product skeleton and collections domain
- `apps/cuentas-claras/{api,web,backoffice}` and `@followup/api-client-cuentas-claras`,
  reusing core, `@followup/ui`, the onboarding wizard and the simulator.
- **Invoices** context: clients (the companies that owe), invoices with amount,
  due date and status (pending, promised, paid, overdue).
- CSV import of clients and invoices with validation and an error report.

**Done when:** a service company signs up with the same onboarding and sees its
imported invoices in the panel.

### Day 8: scheduling, reminders and payments
- **Scheduling** context in core: jobs table in Postgres and a small worker process.
- Reminder policy per tenant with defaults: 3 days before, on the due date, 7 days after.
- Reminders sent with the approved WhatsApp utility templates.
- **Payments** context: Mercado Pago payment link per invoice, and the payment
  webhook marks the invoice as paid and cancels pending reminders.

**Done when:** an invoice due in the test data triggers a reminder on your phone,
you pay it with a Mercado Pago test user, and the invoice turns paid.

### Day 9: the collections agent and approvals
- **Collections** graph that handles replies:
  - "Ya pagué": asks for the receipt and marks the invoice for review.
  - "Mandame la factura": sends the invoice details.
  - "¿Puedo pagar el 15?": creates a payment promise that needs approval.
- **Approval** context in core: approval requests with one-tap approve/reject in `web`,
  and the agent continues the conversation after the decision.
- Dashboard: total owed, payment promises, and money recovered this month.

**Done when:** you reply "puedo pagar el viernes" to a reminder, approve the promise
from the panel, and the client receives the confirmation.

### Day 10: hardening, deploy and launch kit
- Deploy Cuentas Claras to Oracle; both products share the Supabase database.
- Error monitoring and alerts on failed webhooks and failed reminders.
- Full fresh-account test of both products from sign-up, with a stopwatch.
- Landing page per product with the pitch and a sign-up button.
- Pilot kit: demo video for Cuentas Claras, outreach message, list of the first
  10 prospects per product.

**Done when:** both products run in production, each has a landing page, and you
have pilot conversations scheduled. **Cuentas Claras MVP is demo-ready.**

**Stretch:** ARCA homologation proof of concept (read issued invoices by number).

---

## Checkpoints

| Day | Checkpoint |
| --- | --- |
| 3 | Agent conversation survives an API restart |
| 6 | inmo24x7 demo in production on real WhatsApp |
| 8 | A reminder is sent and a test payment marks the invoice as paid |
| 10 | Both products live with landing pages and pilots scheduled |

## Main risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Tech Provider verification not approved in time | Manual number connection from the backoffice; same customer flow later |
| WhatsApp templates rejected | Rewrite as neutral utility text and resubmit early (day 1, not day 8) |
| Oracle ARM capacity unavailable | Google Cloud Run for the API, same Supabase database |
| LLM rate limits during tests | Fake LLM in tests; real model only in manual demos |
| A day overruns | Move its stretch items to the backlog; keep tests and deploy |

## Daily routine

1. Write the day's OpenCode prompt from this file (one section per prompt).
2. Ask for the plan first and confirm it.
3. Review the diff, run the app, try the "Done when" check yourself.
4. Commit with green CI and update this file with what moved.
