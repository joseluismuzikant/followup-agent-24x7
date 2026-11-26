# followup-agent-24x7 roadmap: inmo24x7 first

The focus is **inmo24x7**, the core real estate product. It runs in production on the shared
core (Oracle Cloud + Supabase). **Cuentas Claras moves to a future phase** (section 7). Its
plan, Days 9–12, its screens and its risks stay in
[`cuentas-claras-roadmap.md`](cuentas-claras-roadmap.md).

Every screen element is specified in [`screens-spec.md`](screens-spec.md). The original
12-day plan, day by day, is in this file's git history.

Updated: 26/11/2026.

**Order of work:**

1. **3a. Full Meta integration**: real agencies on their own number. Top priority.
2. **5a. Blue/green deploys (A/B slots)**: right after 3a.
3. **Section 4**: follow-ups, reminders, Google Calendar, the weekly summary, billing.
4. **Section 6: rental guarantees**:
   - 6a, the MCP server;
   - 6b, prequalification in the chat.

   The research and the provider contacts in 6a have lead time. They can start in parallel,
   because they are not code.
5. **Section 7, future phase**: Cuentas Claras.

## 1. Status: done and in production

| What | PR |
| --- | --- |
| Days 1–3: identity and app shell, the onboarding wizard and agent configuration, conversation runtime and simulator | #1–#4 |
| Day 4: properties (CSV/XLSX import), the lead agent, local development without external services | — (commit `75d4d94`, no PR) |
| Day 5: WhatsApp messaging, the job queue and worker, new-lead emails | #5 |
| Day 6: inbox with takeover and visit confirmation, dashboard KPIs | #6 |
| Day 7: Embedded Signup, connection health, backoffice parity, production deploy, backups and rehearsal | #7 |
| Day 7C: Sentry, Loki + Alloy + Grafana, backoffice Errores and Consumo (LLM cost per business) | #8 |
| Day 8: the platform is multi-product (tenants, profiles and job queues per product, migration branches, `packages/platform`, `@followup/app-shell`); invite-only accounts with passwords; the inmo24x7.com look | #9–#11 |
| WhatsApp in production with the Meta test number: webhook, system-user token, manual connection | #7, #10 |
| WhatsApp fixes: Argentine mobiles without the 9 in the Cloud API `to`, longer `name_status` (`AVAILABLE_WITHOUT_REVIEW`) | #10 |
| Automatic deploy after a merge, with approval, syncing the deploy files to the VM | #12 |
| Daily encrypted backups (`pg_dump` → age → rclone) with a tested restore | #7 |
| Grafana and Loki on the VM; LangSmith tracing (14-day retention and a spend limit, set in LangSmith) | #8 |
| Panel responsive on phones | #13, #14 |
| Property conditions: requirements (accepted guarantees, minimum term…) and features, from the spreadsheet to the chat | #16 |
| LLM: OpenAI GPT-5.4 nano in production, with `LLM_REASONING_EFFORT`; DeepSeek no longer used (the provider stays in the code) | #16 |
| "BAJA" opt-out, contact data deletion and account closure | #17 |
| Integrations: Tokko Broker (property import every 6 h, qualified leads as web contacts), signed lead webhook, website script "Consultar por WhatsApp" with the property already identified | #18 |
| Deploy hardening: pulls with timeouts and a retry, time limits on migration and `compose up`, image pruning (last 3 tags), a 30-minute job limit, SSH keepalives. Production deploys from CI succeeded after every merge from 21/11 to 24/11/2026 | #19, #20 |
| Sign-in legal links; CI tests branches through their PR and cancels outdated runs | #21, #22 |
| Inicio after login; the wizard only while the business is missing | #23 |
| Audio messages transcribed for Sofía; "Probar el agente" after signing in; Consumo shows audio usage | #24 |
| 3c: load a property from its publication link or its pasted text ("Cargar desde un link"), and "Actualizar desde el link" | #25 |
| Lead agent hardening (phases 0–1): golden conversations; lead and property text only in user-role DATA; input and output guards; Sofía answers the lead's questions from the options shown; a changed search answer searches again; per-turn limits (model calls, tokens, time); the last attempt hands off instead of failing silently; the stall policy (offer a person, then a `stalled` hand-off) | — (feature/agent-hardening) |
| Landing www.inmo24x7.com with the legal pages (privacidad, términos, eliminación de datos, acuerdo de tratamiento de datos) and the demo video | outside this repo |
| Meta: business verified (18/11/2026); Tech Provider app review submitted (19/11/2026, up to 20 days) | outside this repo |

**Still pending from the items above:**

- The Tokko integration is beta. Five points need checking with a real agency's key
  ([`integrations.md`](integrations.md), "To verify with a real key").
- 3c needs checking with the pilot agency's own links (see "3c" in section 4).
- The agent hardening needs checking with the real model (`LLM_MODEL`): how often answers are
  deferred, whether GPT-5.4 nano fits the output caps (`LLM_REASONING_EFFORT=minimal`), and
  the `agent_terminated` logs of the first weeks ([`go-live.md`](go-live.md), 12c).

## 2. In progress

**3a, the parts that don't wait for Meta's approval** (section 3, "3a.1"). The app review
answer is expected by 09/12/2026. Until then, the code for coexistence, templates and health
can be built and tested with the test number.

## 3. Next objective: real agencies on their own number

**Done when (for the whole section):**

- a real agency connects its own number from the panel and works with it;
- a deploy doesn't interrupt it (5a);
- a bad deploy is rolled back in seconds (5a).

**Decision of 21/11/2026, still valid: photos come from the listing's own link, for now.**

- Properties keep being uploaded with their own link. It is required in the form and in the
  CSV.
- Sofía already answers with that link. Each option is its own WhatsApp message with the link
  and its preview (`leads/whatsapp.py`, `preview_url`), so WhatsApp shows the photo and title
  of the listing's own page. That is how leads see photos for now.
- 3b (storing photos) is postponed (section 4, "Postponed"). 3c (importing a property by
  reading its link) is done (#25). No scraping of portals.

### 3a. Full Meta integration (top priority)

**Already in the code:**

- Embedded Signup v4.
- Connection health: auth errors, `account_update`, a 6-hour check. `quality_rating` and
  `name_status` are stored.
- Meta send errors mapped to Spanish messages for the panel. For example, "Falta un medio de
  pago en Meta" (131042) and "Falta aprobar el nombre visible" (131037). They appear only
  after a send fails.
- A visit-confirmation template per connection, used after 24 h. Its name is typed in the
  backoffice, and the template is created by hand in WhatsApp Manager.
- Core parses `message_template_status_update` (`messaging/domain/webhook.py`). Cuentas
  Claras (#15) creates templates in each business's WABA through the API
  (`reminders/infrastructure/template_graph.py`). **inmo24x7 uses neither yet.** Move
  template creation into the shared core or platform, and reuse it; don't copy it.

#### 3a.1 Build now: doesn't need the app review

- **Coexistence with the WhatsApp Business app:**
  - the agent keeps using the app on the phone, and Sofía answers through the API;
  - subscribe to and handle the app's message echoes (`smb_message_echoes`). Today nothing
    handles them;
  - a reply the agent writes from the phone is stored in the inbox, and Sofía pauses that
    conversation, as on a panel takeover;
  - decide what to do with the chat history that coexistence offers to import.
- **Templates per agency**, created through the API in each agency's WABA:
  - which ones: visit confirmation, visit reminder (4.2), follow-up (4.1);
  - category: utility, as neutral text. Marketing costs more and is reviewed more strictly;
  - status sync through the `message_template_status_update` webhook, wired into inmo24x7,
    plus a periodic sync;
  - the panel says when a template is pending or rejected, and sending falls back to "only
    inside the 24 h window";
  - the template name typed in the backoffice goes away.
- **Webhook fields** subscribed and handled per WABA:
  - `messages`, `account_update`, `message_template_status_update`;
  - the echo fields for coexistence.
- **Health per agency** in the backoffice:
  - quality rating and display-name status, both stored already;
  - messaging limit tier, not read today;
  - "payment method missing at Meta", detected before a send fails, not only after an error
    131042 as today.
- **Terms acceptance in the panel.** The owner accepts Términos and the data processing
  agreement on first sign-in. Store the version and the date. Today nothing records it.
- **Disconnection and reconnection by the agency.** Disconnecting removes the app from the
  WABA (`subscribed_apps` DELETE, already in the Graph client) and stops sending. The
  connection can be made again later.

#### 3a.2 Approval and compliance

| Item | Status | Done when |
| --- | --- | --- |
| Business verification | Done (18/11/2026) | — |
| Tech Provider app review: the WhatsApp permissions in advanced access | Submitted 19/11/2026; answer by 09/12/2026 | Approved; if rejected, fix and resubmit within 2 days |
| App published (Live mode), with the privacy, terms and data deletion URLs of the landing | Waits for the review | Production Embedded Signup works for an account outside our business |
| Display name of each agency's number | Per agency, at onboarding | `name_status` approved, shown in the backoffice |
| Templates approved per agency | 3a.1 | The three templates approved in the pilot's WABA |
| Messaging policy: Sofía is a task-specific assistant for the agency's listings and visits, not a general-purpose chatbot; a human can always take over; BAJA is honoured | Built (#6, #17) | Checked against Meta's current WhatsApp Business policy before going live, and the prompt keeps Sofía on topic |
| Opt-in: leads write first; templates go only to leads who asked for a visit or a follow-up | Policy decided; enforced in 4.1 and 4.2 | No template to a lead who never wrote or wrote BAJA |
| Meta charges per template message, to the agency's card in its WABA | To explain at onboarding | The onboarding guide says who pays and roughly how much |
| Data protection (Ley 25.326): the agreement with each agency, deletion on request, account closure | Built (#17, landing) | The agency accepts it in the panel (3a.1) |

#### 3a.3 Go live with the pilot agency

- Production Embedded Signup with a **real** agency number, with coexistence.
- **Onboarding guide** for a new agency, used as a video-call checklist:
  1. invitation;
  2. Términos and the data processing agreement (3a.1);
  3. Embedded Signup;
  4. card in WhatsApp Manager;
  5. properties and conditions (CSV, Tokko or "Cargar desde un link");
  6. agent settings;
  7. first test from a phone that isn't the agency's.
- **Support runbook:** what to do when:
  - the number disconnects;
  - quality drops to red;
  - a template is rejected;
  - the payment method fails;
  - the agency wants to leave.

**Done when:**

- a real agency connects its own number from the panel;
- a lead writes and Sofía answers;
- the agent replies from the phone, and Sofía pauses that conversation;
- the visit-confirmation template, created through the API, goes out after 24 h;
- the backoffice shows that agency's health;
- a second agency is onboarded with the guide alone, in under 30 minutes.

### 5a. Blue/green deploys (A/B slots), right after 3a

Moved up from "Operations". With real agencies on their own numbers, a deploy must not drop
webhooks or replies, and a bad version must be undone in seconds.

**How it works:**

- Two app slots on the same VM, **A** and **B**: two Compose projects for `api`, `web` and
  `backoffice`. The database, Caddy and Loki/Alloy/Grafana are shared.
- A deploy starts the new version in the **idle** slot. It checks `/health/ready` and a
  smoke test there through an internal port, before any real traffic. The smoke test covers
  sign-in, a panel page, and a signed test webhook that is ignored.
- It then **switches Caddy's upstream** to that slot with a graceful reload.
- It **watches the new slot for a few minutes** after the switch: health, the 5xx rate in
  Loki, Sentry. If they fail, it switches back automatically and the deploy is marked failed.
- The old slot keeps running untouched, for an instant rollback (switch back), until the
  next deploy reuses it. Pruning already keeps the last 3 image tags.

**Rules it needs:**

- Database migrations must be **backward compatible**: expand, deploy, then contract in a
  later release. Both versions share the database during the switch. This is already the rule
  (ARCHITECTURE.md, "Migrations").
- The **worker** runs only in the active slot, so there is one job consumer. On the switch,
  the old worker stops taking jobs and finishes the ones it has before the new one starts.
- Webhooks keep working through the switch, because Caddy's reload is graceful.
- The rehearsal (`deploy/rehearsal.md`) covers a switch and a rollback.

**The Deploy workflow** shows which slot is live and offers "Volver a la versión anterior"
(switch back) without rebuilding.

**Done when:**

- a deploy has zero failed requests during the switch, measured with a load loop that
  includes webhooks;
- a manual rollback takes seconds;
- a version with a failing health check is never left live.

## 4. After that

Ordered by value for the first clients. Revisit the order with their feedback.

1. **Follow-up of leads that stop answering.** A template at 24 and 48 h, from 3a. A lead who
   wrote "BAJA" is never written to again.
   **Done when:** a lead who stops answering gets one follow-up, a BAJA lead gets none, and
   the inbox shows both.
2. **Visit reminder the day before, with confirmation.** It uses the reminder template
   from 3a.
   **Done when:** the lead gets the reminder, answers, and the visit shows as confirmed or
   cancelled in the panel.
3. **Google Calendar.** Propose slots from the agent's real calendar, and add confirmed
   visits to it.
   **Done when:** Sofía never offers a busy slot, and a confirmed visit appears in the
   calendar.
4. **Weekly summary email for the agent:** leads, qualified leads, visits requested and
   visits avoided.
   **Done when:** every agency owner gets it on Monday morning with the previous week's
   numbers, and the numbers match Inicio.
5. **Plans and automatic billing** (a 14-day trial, a Mercado Pago subscription), once there
   are about 10 clients.
   **Done when:** a trial ends, the agency pays from the panel, and an unpaid agency is
   suspended without manual work.
6. **Later, if clients ask:**
   - several agents per agency, with lead assignment;
   - an LLM model per agency, set in the backoffice only, from an allowlist of tested models;
   - cost limits per agency.

### Agente con herramientas (híbrido), para más adelante

A bounded tool-calling step after `extract`. When the simple answer step cannot answer the
lead's question from the options already shown, it would call read-only tools (an offered
property, a comparison, requirements, a search preview, the agency's info) through a gateway
that the application controls. The design is in
[`hybrid-agent-design.md`](hybrid-agent-design.md).

**Build it when at least one of these is true**, measured with the hardening's logs and the
`llm_usage` table:

1. **Unanswered questions are frequent.** With 3 or more agencies live for 4 weeks or more,
   or 300 or more real conversations, more than about 15 % of the turns with `needs_answer`
   end deferred ("lo consulto"). The inbox also shows that the data existed somewhere the
   simple answer step couldn't reach.
2. **The properties get richer data.** Description, m², expensas, amenities or photos (3b)
   come in from the form, imports or Tokko, and answering needs searching or comparing beyond
   the options already shown.
3. **New multi-step capabilities need tool use:**
   - visit times from the agent's real calendar (4.3);
   - several properties in one visit;
   - "show me similar ones" across the whole catalog.
4. **A model with reliable tool calling fits the cost.** The cost per conversation stays
   within what the plan price allows (see Consumo).

Until then, the hardening's answer step (`ANSWER_QUESTION` plus the guards) is the supported
design.

### Postponed: property photos (decision of 21/11/2026)

They wait because each option's link preview already shows leads the listing's own photo and
title, and 3a is what lets real agencies use the product.

#### 3b. Property images

**Photos:** up to 5 per property, one marked as the cover. Sources:

- upload in the property form, by drag and drop or the phone camera;
- a new optional `imagenes` column in the CSV/XLSX, with URLs;
- the import from a link (3c);
- Tokko's photos. The integration reads none today.

**Storage:**

- Oracle Object Storage, at a public, unguessable path per agency. Listing photos are public
  anyway.
- Resized to about 1280 px and about 200 KB, JPEG or WebP.
- **EXIF removed**, which drops the GPS position.
- Deleted with the property and with account closure. Add them to the table-scan tests in
  `privacy/`.

**Sofía:**

- sends the **cover photo** of each option as a WhatsApp image message, captioned with
  title, price, address and link;
- sends more photos when the lead asks ("¿tenés más fotos?") or chooses a property.

**Panel:** thumbnails in the property list and on the inbox cards.

**Done when:** an agent uploads photos from the phone, and a lead on WhatsApp gets the
options with their cover photos and can ask for more.

### 3c. Import a property from its publication link (done, #25)

The agent pastes the link of **their own** publication (Zonaprop, Argenprop, RE/MAX, their
website) in Propiedades → "Cargar desde un link":

- `POST /properties/from-link` reads the page once, with our user agent
  (`inmo24x7/1.0 (+https://www.inmo24x7.com)`). It is guarded against SSRF:
  - http/https on standard ports only;
  - public addresses only, checked on every redirect (at most 3), and the connection goes to
    the checked address;
  - 10 s, 3 MB, `text/html` only;
  - no cookies, no retries.
- The structured data comes first (schema.org JSON-LD, Open Graph, `<h1>`/`<title>`, meta
  description). The model (`LLM_MODEL`, prompt `listing_extract.v1`) reads the visible text
  only when title, operation, price, zone or rooms are still missing. Its calls are
  `llm_usage` rows (operation `read_listing`, channel `panel`).
- Values go through the CSV's parsing. The `link` is stored without tracking parameters.
  The cover image is for the preview only (photos are 3b).
- **Portals that block us** (Zonaprop answers 403): the dialog switches to "Pegar texto de
  la publicación" and keeps the link. `POST /properties/from-text` reads the copied text
  with the same model and mapping. The block is never worked around.
- The form opens **pre-filled**; what the model read is marked "Revisá este dato".
  Nothing is saved until "Guardar". A link already loaded offers "Ya cargaste esta propiedad
  — Abrirla".
- "Actualizar desde el link" (manual properties only) re-reads the link or a pasted text and
  shows the changes (title, price, status…) to apply field by field.
- Limited to 20 reads per agency and hour (`property_link_read` in the audit log, never
  the link).

**To verify with the pilot agency's own links:**

- which portals block us besides Zonaprop;
- which ones publish JSON-LD or Open Graph with the price and rooms;
- whether Argenprop's and RE/MAX's titles say the zone;
- whether the model keeps the price apart from the expensas on real texts.

## 5. Operations

5a (blue/green deploys) moved up to section 3, right after 3a.

### 5b. Before or with the first paying clients

| Task | Done when |
| --- | --- |
| LangSmith sampling at 0.25 in production (`LANGSMITH_TRACING_SAMPLING_RATE`; `.env.production.example` already says 0.25) | The VM's `.env.production` has 0.25 and LangSmith shows about a quarter of the turns |
| Let the Grafana silence on "Sin webhooks de Meta" expire, and make the alert smarter: 24 h of silence on numbers that had traffic | A quiet night with no leads doesn't fire it; a broken webhook on an active number does |
| Alerts per agency: quality rating down, number disconnected, template rejected (from 3a's health) | The owner gets an email and the backoffice shows it, within an hour |
| Supabase Pro when the database nears 400 MB | The project is on Pro before it reaches 500 MB |
| A Vercel plan for a commercial site, or move the landing | The landing runs on a plan that allows commercial use |

## 6. Rental guarantees

Most rental leads stall on the guarantee. Today Sofía asks "¿Qué garantía tenés?" with fixed
answers (`leads/conditions.py`: propietaria, seguro de caución, ninguna, otra) and checks
them against the property's accepted guarantees (#16). It doesn't help a lead who has none.

### 6a. Rental guarantee MCP server (an independent product)

An MCP server, sold separately, for agencies, other chatbots and AI assistants. inmo24x7 is
its first client (6b).

**What it does (its tools):**

- **Prequalify an applicant** against each provider's requirements, from their income
  (amount and proof), employment (employee, monotributo, autónomo, retired), seniority, rent
  and documents. Each provider gets "likely yes", "likely no" (with the reason) or "missing
  data" (with what is missing).
- **Compare** the compatible providers: cost (as a share of the contract or the rent),
  installment plans, requirements and coverage (rent, expensas, damage, eviction costs).
- **List the documents** each provider asks for, so the chat collects them once.
- **Quote** a guarantee for a rent and a term, with each provider's own calculator when
  there is an integration, or the published rules otherwise. Each quote says "estimated".
- **Refer** an applicant to a provider: a referral link or code, and the data the applicant
  agreed to send.

**Providers:**

- Finaer, Respaldar, Monclair, Garantía Ya, and Sancor (seguro de caución).
- Each provider's rules are versioned data (requirements, prices, plans, coverage), with
  their source and the date checked. They are not code, so updating them needs no deploy.
- Every rule set is reviewed at least monthly.

**To investigate before building:**

- Finaer's and Respaldar's online calculators: is there a public or partner API? Do they
  allow embedding? What are their terms of use? The calculators are only used with
  permission, and never scraped against their terms.
- Partner or referral programmes at all five providers: commission, tracking, and what data
  they accept.
- **Regulation:**
  - seguro de caución is insurance, supervised by the SSN. Does a referral commission
    require a registered insurance intermediary (Ley 22.400), or a partnership with one?
  - tenant data is personal data (Ley 25.326), and income proof is sensitive: consent,
    purpose, retention and deletion.

**Monetization:**

- subscriptions by plan (prequalifications per month) for agencies and integrators;
- referral commissions from the providers, where the regulation allows them;
- inmo24x7 agencies get it included in their plan, or as an add-on (decide with 4.5).

**Architecture:**

- Its own app in this monorepo, on the shared core (tenants, API keys per client, usage
  metering, audit).
- Exposed as a remote MCP server: Streamable HTTP, auth per client.
- It stores no documents by default. It reads what it is given, returns the result, and
  keeps only the usage row and the referral. Storing documents is an explicit option per
  client, with a retention period.

**Done when:**

- an external MCP client (Claude, or another assistant) prequalifies a sample applicant
  against the five providers and gets a comparison with estimated costs;
- a usage row is billed to that client;
- the rule sets show their source and the date checked.

### 6b. Guarantee prequalification in the chat

It depends on 6a and on 3a (real numbers).

- Sofía asks a rental lead whether they **already have a guarantee**. Owner's property
  guarantee or caución already taken: as today, checked against the property.
- If they have none, or want a caución, Sofía offers to check which ones they could get.
  Before asking for data or documents, she asks for **consent** to use them for that and to
  share them with the provider they choose.
- She collects what 6a's document list needs:
  - income and employment type, seniority. Today the agent never reads income and the
    output guard blocks replies that mention it (agent hardening): 6b changes that rule
    deliberately, only for this step and with consent;
  - documents sent on WhatsApp (DNI, pay slips, monotributo records), as photos or PDFs.
    Reading documents is new: today only text and audio are read (#24).
- She calls the MCP server (6a) and presents the **compatible options**: provider, estimated
  cost, installments, main conditions. Each one says it is an estimate, and the provider
  decides.
- The lead chooses one. Sofía sends the **referral** (link or contact) and tells the agent.
- The **result is stored in the CRM**:
  - on the lead: status (sin garantía, precalificado, derivado a <proveedor>) and the
    options shown;
  - in the inbox card, in the qualified-lead email, and in the Tokko and webhook exports.
- **Panel:** each agency turns it on or off, and chooses which providers to offer.
- Documents follow 6a's rule: not kept after the prequalification unless the agency turns
  storage on. Contact deletion and account closure remove them (`privacy/`).

**Done when:**

- a lead without a guarantee is prequalified in the chat, sees two or more options with
  estimated costs, and is referred to one;
- the agent sees the result on the lead without asking;
- a lead who says no to consent is never asked for documents.

## 7. Future phase: Cuentas Claras

On standby, not removed. Nothing in its code is deleted, and its compose profile stays off in
production. The plan, the channel decision (email and SMS rather than WhatsApp) and the risks
are in [`cuentas-claras-roadmap.md`](cuentas-claras-roadmap.md).

- **Revisit when:** 3a, 5a and section 4 up to billing (4.5) are done, and inmo24x7 has
  steady paying clients.
- **Meanwhile:** shared work that started in Cuentas Claras moves to the core, and inmo24x7
  reuses it. Templates through the API (3a) are the first case.

## Things with lead time

These don't depend on code, and some take days. Start them before the item that needs them.

| Task | Needed by | Typical lead time |
| --- | --- | --- |
| Meta Tech Provider app review (submitted 19/11/2026) | 3a | Up to 20 days (answer by 09/12/2026) |
| A real agency willing to connect its number, with the WhatsApp Business app on its phone | 3a | Days |
| A card at Meta for that agency's WABA (WhatsApp Manager) | 3a | Minutes, done by the agency |
| Template approval in the pilot's WABA | 3a, 4.1, 4.2 | Minutes to a day per template |
| Own listing links from the pilot agency on Zonaprop, Argenprop and RE/MAX, to verify 3c | 3c (done; verify) | Minutes |
| A real Tokko key from an agency, to close the "to verify" list | Tokko out of beta | Days |
| Google Cloud OAuth app with the Calendar scope (verification for sensitive scopes) | 4.3 | Days to weeks |
| Mercado Pago subscription account | 4.5 | Days |
| Contact with Finaer, Respaldar, Monclair, Garantía Ya and Sancor: requirements, calculators or APIs, partner and referral programmes | 6a | Weeks |
| Legal advice: insurance intermediation (SSN, Ley 22.400) for caución referrals; consent and retention for tenant documents (Ley 25.326) | 6a, 6b | Weeks |
| Oracle Object Storage bucket and an API key for the VM | 3b (postponed) | Minutes |

## Checkpoints

| Checkpoint | Proves |
| --- | --- |
| Two production deploys in a row without touching the VM (done: every merge from 21/11 to 24/11/2026 deployed from CI) | Deploy hardening |
| A real agency's own number answers a lead, with the agent replying from the phone | 3a |
| A deploy and a rollback with real agencies connected and zero failed requests | 5a |
| The first paying client | 4.5 and 5b |
| A lead without a guarantee referred to a provider from the chat | 6a and 6b |

## Main risks and fallbacks

| Risk | Fallback |
| --- | --- |
| The app review is rejected or takes longer than 20 days | Fix what Meta asks and resubmit; meanwhile, keep connecting numbers by hand in the backoffice (it works today) |
| Coexistence doesn't deliver the phone's replies as expected | The agent takes over from the panel's inbox (takeover works today) and Sofía pauses that conversation |
| Templates rejected | Rewrite them as neutral utility text and resubmit early |
| Meta's policy on AI assistants changes or is read strictly | Keep Sofía task-specific with human takeover; follow the policy's changes before each release |
| A switch between slots drops requests or runs two workers (5a) | Automatic switch-back on failed health; the worker starts only after the old one stops |
| A portal blocks reading the page (3c; Zonaprop does) | The agent pastes the publication's text, or completes the form; never work around the block |
| Guarantee providers don't offer an API or a referral programme (6a) | Published rules as versioned data, and referral by link or contact without a commission; sell 6a by subscription |
| Caución referrals need a licensed insurance intermediary (6a) | Partner with a registered productor asesor de seguros, or refer without a commission |
| Tenant documents leak or are kept too long (6b) | Not stored by default; consent first; deletion with the contact; access in the audit log |
| Image storage costs or upload sizes grow (3b, postponed) | Resize and compress on upload; keep the 5-photo limit |
| Tokko's real API differs from the docs | The differences stay in `integrations/tokko.py`; the integration stays beta until checked |
| Oracle ARM capacity unavailable | Google Cloud Run for the API, with the same Supabase database |
| LLM costs grow with real traffic | Backoffice Consumo and the monthly cost alert; GPT-5.4 nano by default |

## Screens

All inmo24x7 screens in [`screens-spec.md`](screens-spec.md) (S1–S9) are built. Changes still
to come:

| Item | Screens it changes |
| --- | --- |
| 3a | S4 (live Embedded Signup, coexistence, terms acceptance), S9 (Meta health), templates in the backoffice |
| 5a | The Deploy workflow (live slot, "Volver a la versión anterior"); no panel screen |
| 3b (postponed, section 4) | S7 (photos in the form and list), S6 (thumbnails), S3 (image messages) |
| 3c (done) | S7 ("Cargar desde un link", "Actualizar desde el link") |
| 4.1–4.4 | S6 (follow-ups and reminders), Configuración (Google Calendar), the weekly email |
| 6b | S6 (the guarantee result on the lead card), Configuración (turn it on, choose providers), S3 (options in the chat) |

## Daily routine

1. Write the work block's prompt from this file, one item per prompt.
2. Ask for the plan first and confirm it.
3. Review the diff, run the app, and try the "Done when" check yourself.
4. Commit with green CI and update this file with what moved.
