# Cuentas Claras roadmap

## Status: standby

| Part | PR | Status |
| --- | --- | --- |
| Day 8: product skeleton, Clientes, C2 Facturas with CSV import | #9–#11 | Merged |
| Day 9A: WhatsApp reminders, templates per business, Argentine holidays, the scheduler | #15 | Merged |
| Day 9B: Mercado Pago | — | Not started |
| Days 10–12 | — | Not started |

- No Cuentas Claras code is deleted.
- Production keeps it off: its compose profile `cuentas-claras` stays disabled.
- **Future phase** (decision of 26/11/2026): revisit when inmo24x7's 3a, 5a and billing
  (4.5) are done and it has steady paying clients ([`roadmap-mvp.md`](roadmap-mvp.md),
  section 7).

The active roadmap is [`roadmap-mvp.md`](roadmap-mvp.md) (inmo24x7).

### Why

- The WhatsApp Business Messaging Policy prohibits "debt collection".
- A business's own invoice reminders may be acceptable as utility messages, but Meta decides
  at its discretion. A product whose main channel can be cut off by one policy reading is not
  a safe start.

### Channel options to validate before resuming

| Channel | Pros | Cons | Cost | Rules |
| --- | --- | --- | --- | --- |
| WhatsApp utility templates for the business's own invoice reminders (polite, no pressure) | The channel clients answer; Day 9A is built for it | Meta may reject the templates or restrict the number; the policy names debt collection | Meta's utility price per message | Validate with Meta or a Business Solution Provider first |
| SMS through a provider (for example Twilio, Infobip or a local aggregator) | Works on any phone; no Meta policy | No rich content; two-way replies are harder; sender IDs vary by carrier | Much higher per message than WhatsApp; get quotes | Argentine rules on collection practices: respectful contact, reasonable hours, no third parties (Ley 24.240, art. 8 bis, "trato digno"); the "No Llame" registry where it applies |
| Email | Free and simple; room for the invoice and the payment link | Lower open rates | Practically free (SMTP provider) | Sender authentication (SPF, DKIM, DMARC); an unsubscribe link |
| A mix | Email always, plus SMS or WhatsApp as the reminder channel depending on validation | Two channels to operate | Email plus the chosen channel | The rules of each channel used |

### Direction for when it resumes

- **The channel:** notify invoices and reminders by **email and SMS**, not WhatsApp, to stay
  clear of Meta's restriction. WhatsApp only if Meta explicitly allows a business's own
  invoice reminders.
- **What stays from Day 9A:** the scheduler, the reminder policy, the holidays and the payment
  link page.
- **What changes:** only the channel. A `ReminderChannel` port with email and SMS adapters
  replaces the direct WhatsApp send. The WhatsApp code stays as one more adapter.
- **What follows from it:** the replies Day 10 handles arrive by email or SMS. Its agent
  works on the channel's messages, not on a WhatsApp thread.

---

## The plan from Day 9 (as written before standby)

Revisit each day against the direction above when work resumes.

### What "MVP" means here

- A service company signs up with the same onboarding, imports its clients and invoices from
  a CSV, and connects its own Mercado Pago account.
- Automatic reminders with escalation and a Mercado Pago payment link.
- Payments through Mercado Pago mark invoices as paid automatically.
- The agent answers typical replies. Payment promises and installment plans need the
  owner's one-tap approval.
- A dashboard with total owed, payment promises, and money recovered this month.

### Day 9: scheduling, reminders and payments

- C4:
  - editable reminder sequence and send window;
  - Argentine holidays;
  - pause on a payment promise;
  - escalation to the owner.
- Templates per tenant with Meta status sync.
- Mercado Pago:
  - OAuth per tenant;
  - a payment link per invoice;
  - a payment webhook that marks the invoice paid and cancels pending reminders.

**Screens:** C4.

**Done when:** an invoice due in the test data triggers a reminder on your phone, you pay it
with a Mercado Pago test user, and the invoice turns paid.

**9A done (#15):**

- **WhatsApp:** shared with inmo24x7, not copied (`followup_platform.whatsapp`,
  `@followup/app-shell/whatsapp`), with Cuentas Claras's own Meta app.
- **C4:**
  - the editable sequence and send-window presets;
  - "No enviar en feriados": the `holidays` package plus `holidays_ar.toml`, with 2026–2027
    verified in tests;
  - "Pausar si el cliente prometió pagar";
  - the escalation step emails the owner and stops the invoice's reminders.
- **Templates per business:** created in its WABA on connect, with Meta's status (the webhook
  and a 6-hourly sync). Edits become new versions.
- **Sending:**
  - the daily planner and the send job, at most one reminder per client per day, with
    several invoices in one message;
  - `reminder_events` and "Lo próximo";
  - promises and "No enviar recordatorios";
  - replies stored and emailed to the owner;
  - the payment link page with transfer details.

**9B (Mercado Pago) not started.**

### Day 10: the collections agent and approvals

- A **Collections** graph that handles replies: "Ya pagué", "Mandame la factura",
  "¿Puedo pagar el 15?".
- C3: promise, installment plan and payment verification cards.
- Receipt files received and stored; payment verified against Mercado Pago.
- Counter-offers and "Responder yo", reusing inmo24x7's takeover.
- After a decision, the agent continues the conversation.

**Screens:** C3.

**Done when:** you reply "puedo pagar el viernes" to a reminder, approve the promise from the
panel, and the client receives the confirmation.

### Day 11: dashboard, backoffice and deploy

- C1 dashboard:
  - aging buckets and the attention list;
  - today's activity and the next send time;
  - the Aprobaciones count badge.
- C5 backoffice:
  - failed sends with retry;
  - template health;
  - Mercado Pago webhook health;
  - the tenants table.
- Turn on the `cuentas-claras` compose profile in production. Both products share the
  Supabase database.

**Screens:** C1, C5.

**Done when:** the dashboard reflects imported invoices and reminders, and the backoffice
shows failed sends with a working retry.

### Day 12: hardening, monitoring and launch kit

- Alerts on failed reminders.
- A full fresh-account test, from the invitation, with a stopwatch.
- A landing page with the pitch.
- Pilot kit:
  - a demo video;
  - an outreach message;
  - a list of the first 10 prospects.

**Done when:** it runs in production, has a landing page, and you have pilot conversations
scheduled. **Cuentas Claras MVP is demo-ready.**

**Stretch:** an ARCA homologation proof of concept (read issued invoices by number).

### Post-MVP

- ARCA integration (reading issued invoices). The CSV import covers the MVP, and C2 shows only
  the "coming soon" notice.
- Bank statement import and receipt verification with OCR. Day 10 uses the received receipt
  with manual verification.

## Screens

| Day | Screens |
| --- | --- |
| 8 (done) | C2, Clientes |
| 9 (9A done) | C4 |
| 10 | C3 |
| 11 | C1, C5 |
| 12 | Launch and hardening |

Nav-only: Plantillas de WhatsApp (Day 9; it depends on the channel decision).

## Things with lead time

| Task | Why | Typical lead time |
| --- | --- | --- |
| Meta or a Business Solution Provider: are a business's own invoice reminders allowed as utility templates? | Decides whether WhatsApp stays a channel | Days to weeks |
| SMS provider account and Argentine sender, with price quotes | The proposed reminder channel | Days |
| Mercado Pago OAuth application with the redirect URL on the production domain | Each business connects its own account | Minutes to days |
| Mercado Pago developer account, test users and credentials | Payment links and payment webhooks | Minutes |
| Cuentas Claras's own Meta app (a Meta app has one webhook URL) | Only if WhatsApp is validated | Days to weeks (verification) |
| `holidays` package (AR) checked for each new year | "No enviar en feriados" must be correct | Minutes |

## Checkpoints

| Day | Checkpoint |
| --- | --- |
| Before resuming | The channel decision is made (table above) |
| 9 | A reminder is sent and a test payment marks the invoice as paid |
| 11 | The dashboard and backoffice reflect live data |
| 12 | Live with a landing page and pilots scheduled |

## Main risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Meta treats invoice reminders as debt collection | Email and SMS through the `ReminderChannel` port; WhatsApp off |
| Reminder templates rejected | Rewrite them as neutral utility text, or move to email and SMS |
| SMS cost per client too high for the pricing | Email as the main channel, SMS only for the due-date and overdue reminders |
| Collection rules (trato digno, hours, "No Llame") not respected | The send window and policy from Day 9A, reviewed against the rules before go-live |
| Mercado Pago OAuth redirect not approved | Manual per-tenant credentials in the backoffice during the pilot |
| Argentine holidays source incomplete for a new year | A manual list in `holidays_ar.toml` |
