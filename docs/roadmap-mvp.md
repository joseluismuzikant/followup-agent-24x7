# followup-agent-24x7 roadmap: inmo24x7 first

The focus is **inmo24x7**. It runs in production on the shared core (Oracle Cloud + Supabase).
**Cuentas Claras is on standby.** Its plan, Days 9–12, its screens and its risks are in
[`cuentas-claras-roadmap.md`](cuentas-claras-roadmap.md).

Every screen element is specified in [`screens-spec.md`](screens-spec.md). The original
12-day plan, day by day, is in this file's git history.

Updated: 21/11/2026.

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
| Property conditions: requirements and features, from the spreadsheet to the chat | #16 |
| LLM: OpenAI GPT-5.4 nano in production, with `LLM_REASONING_EFFORT`; DeepSeek no longer used (the provider stays in the code) | #16 |
| "BAJA" opt-out, contact data deletion and account closure | #17 |
| Integrations: Tokko Broker (property import every 6 h, qualified leads as web contacts), signed lead webhook, website script "Consultar por WhatsApp" with the property already identified | #18 |
| Landing www.inmo24x7.com with the legal pages (privacidad, términos, eliminación de datos, acuerdo de tratamiento de datos) and the demo video | outside this repo |
| Meta: business verified (18/11/2026); Tech Provider app review submitted (19/11/2026, up to 20 days) | outside this repo |
| 3c: load a property from its publication link or its pasted text ("Cargar desde un link"), and "Actualizar desde el link" | — (this branch) |

**Still pending from the items above:**

- The Tokko integration is beta. Five points need checking with a real agency's key
  ([`integrations.md`](integrations.md), "To verify with a real key").

## 2. In progress

### Deploy hardening

Two deploys hung forever pulling images.

- Pull only our app images, one at a time, each with a timeout and one retry. Pull
  third-party pinned images only when they are missing.
- Time limits, with one retry on a timeout, for the migration and `compose up`.
- Prune old app images after a successful deploy, keeping the last 3 tags.
- A 30-minute limit on the GitHub deploy job, and SSH keepalives.

**Status:** merged; 1 of 2 deploys done (#19, #20). The first automatic production deploy
with it succeeded on 20/11/2026, in about 7 minutes, with nobody touching the VM. The merge
of the sign-in legal links (`chore/legal-links-roadmap`) is the second.

**Done when:** it is merged, the rehearsal passes with it, and two production deploys in a
row finish without anyone touching the VM.

## 3. Next objective: real agencies on their own number

3a starts when Meta approves the app review (expected by 09/12/2026).

**Decision of 21/11/2026: photos come from the listing's own link, for now.**

- Properties keep being uploaded with their own link. It is required in the form and in the
  CSV.
- Sofía already answers with that link. Each option is its own WhatsApp message with the link
  and its preview (`leads/whatsapp.py`, `preview_url`), so WhatsApp shows the photo and title
  of the listing's own page. That is how leads see photos for now.
- 3b (storing photos) is postponed (section 4, "Postponed"). 3c (importing a property by
  reading its link) is done: see "3c" below. No scraping of portals.
- 3a, the full Meta integration, stays as the next objective.

### 3a. Full Meta integration

**Already in the code:**

- Embedded Signup v4.
- Connection health: auth errors, `account_update`, a 6-hour check. `quality_rating` and
  `name_status` are stored.
- A visit-confirmation template per connection, used after 24 h. Its name is typed in the
  backoffice, and the template is created by hand in WhatsApp Manager.
- Cuentas Claras (#15) already creates templates in each business's WABA through the API and
  follows `message_template_status_update`. Reuse that; don't copy it.

**To build:**

- **Go live.** Publish the app (Live mode). Test production Embedded Signup with a **real**
  agency number, including **coexistence** with the WhatsApp Business app:
  - the agent keeps using the app on the phone;
  - Sofía answers through the API;
  - human replies from the phone are seen and respected: Sofía pauses that conversation.
    Today nothing handles message echoes from the app.
- **Templates per agency**, created through the API in each agency's WABA:
  - which ones: visit confirmation, visit reminder, follow-up;
  - status sync: the `message_template_status_update` webhook plus a periodic sync;
  - the template name typed in the backoffice goes away.
- **Webhook fields** subscribed and handled: `messages`, `account_update`,
  `message_template_status_update`.
- **Health per agency** in the backoffice:
  - quality rating and display-name status, both stored already;
  - messaging limit tier, not read today;
  - "payment method missing at Meta", not detected today.
- **Onboarding guide** for a new agency, used as a video-call checklist:
  1. invitation;
  2. Términos (the panel has no acceptance step today: decide whether the call or a
     checkbox covers it);
  3. Embedded Signup;
  4. card in WhatsApp Manager;
  5. properties and conditions;
  6. agent settings;
  7. first test.

**Done when:** a real agency connects its own number from the panel, a lead writes, Sofía
answers, the agent replies from the phone, and the visit-confirmation template goes out after
24 h.

## 4. After that

Ordered by value for the first clients. Revisit the order with their feedback.

1. **Follow-up of leads that stop answering.** A template at 24 and 48 h. A lead who wrote
   "BAJA" is never written to again.
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

### 3c. Import a property from its publication link (done)

Moved out of "Postponed" and built. The agent pastes the link of **their own** publication
(Zonaprop, Argenprop, RE/MAX, their website) in Propiedades → "Cargar desde un link":

- `POST /properties/from-link` reads the page once, with our user agent
  (`inmo24x7/1.0 (+https://www.inmo24x7.com)`). It is guarded against SSRF: http/https on
  standard ports, public addresses only (checked on every redirect, at most 3, and
  connected by the checked address), 10 s, 3 MB, `text/html`, no cookies, no retries.
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

**To verify with the pilot agency's own links:** which portals block us besides Zonaprop.
Which ones publish JSON-LD or Open Graph with the price and rooms. Whether Argenprop's
and RE/MAX's titles say the zone. Whether the model keeps the price apart from the expensas
on real texts.

## 5. Operations

### 5a. Blue/green deploys (A/B slots)

**How it works:**

- Two app slots on the same VM, **A** and **B**: two Compose projects for `api`, `web` and
  `backoffice`. The database, Caddy and Loki/Alloy/Grafana are shared.
- A deploy starts the new version in the **idle** slot. It checks `/health/ready` and a
  smoke test there through an internal port, before any real traffic.
- It then **switches Caddy's upstream** to that slot with a graceful reload.
- The old slot keeps running untouched, for an instant rollback (switch back), until the
  next deploy reuses it.

**Rules it needs:**

- Database migrations must be **backward compatible**: expand, deploy, then contract in a
  later release. Both versions share the database during the switch. This is already the rule
  (ARCHITECTURE.md, "Migrations").
- The **worker** runs only in the active slot, so there is one job consumer.
- Webhooks keep working through the switch, because Caddy's reload is graceful.

**The Deploy workflow** shows which slot is live and offers "Volver a la versión anterior"
(switch back) without rebuilding.

**Done when:** a deploy has zero failed requests during the switch (measured with a load
loop), and a rollback takes seconds.

### 5b. Before or with the first paying clients

| Task | Done when |
| --- | --- |
| LangSmith sampling at 0.25 in production (`LANGSMITH_TRACING_SAMPLING_RATE`; `.env.production.example` already says 0.25) | The VM's `.env.production` has 0.25 and LangSmith shows about a quarter of the turns |
| Let the Grafana silence on "Sin webhooks de Meta" expire, and make the alert smarter: 24 h of silence on numbers that had traffic | A quiet night with no leads doesn't fire it; a broken webhook on an active number does |
| Supabase Pro when the database nears 400 MB | The project is on Pro before it reaches 500 MB |
| A Vercel plan for a commercial site, or move the landing | The landing runs on a plan that allows commercial use |

## Things with lead time

These don't depend on code, and some take days. Start them before the item that needs them.

| Task | Needed by | Typical lead time |
| --- | --- | --- |
| Meta Tech Provider app review (submitted 19/11/2026) | 3a | Up to 20 days |
| A real agency willing to connect its number, with the WhatsApp Business app on its phone | 3a | Days |
| A card at Meta for that agency's WABA (WhatsApp Manager) | 3a | Minutes, done by the agency |
| Oracle Object Storage bucket and an API key for the VM | 3b (postponed) | Minutes |
| Own listing links from the pilot agency on Zonaprop, Argenprop and RE/MAX, to verify 3c | 3c (done; verify) | Minutes |
| A real Tokko key from an agency, to close the "to verify" list | Tokko out of beta | Days |
| Google Cloud OAuth app with the Calendar scope (verification for sensitive scopes) | 4.3 | Days to weeks |
| Mercado Pago subscription account | 4.5 | Days |

## Checkpoints

| Checkpoint | Proves |
| --- | --- |
| Two production deploys in a row without touching the VM (1 of 2 done, 20/11/2026) | Deploy hardening (2) |
| A real agency's own number answers a lead, with the agent replying from the phone | 3a |
| The first paying client | 4.5 and 5b |

## Main risks and fallbacks

| Risk | Fallback |
| --- | --- |
| The app review is rejected or takes longer than 20 days | Fix what Meta asks and resubmit; meanwhile, keep connecting numbers by hand in the backoffice (it works today) |
| Coexistence doesn't deliver the phone's replies as expected | The agent takes over from the panel's inbox (takeover works today) and Sofía pauses that conversation |
| Templates rejected | Rewrite them as neutral utility text and resubmit early |
| A portal blocks reading the page (3c; Zonaprop does) | The agent pastes the publication's text, or completes the form; never work around the block |
| Image storage costs or upload sizes grow (3b, postponed) | Resize and compress on upload; keep the 5-photo limit |
| Tokko's real API differs from the docs | The differences stay in `integrations/tokko.py`; the integration stays beta until checked |
| Oracle ARM capacity unavailable | Google Cloud Run for the API, with the same Supabase database |
| LLM costs grow with real traffic | Backoffice Consumo and the monthly cost alert; GPT-5.4 nano by default |

## Screens

All inmo24x7 screens in [`screens-spec.md`](screens-spec.md) (S1–S9) are built. Changes still
to come:

| Item | Screens it changes |
| --- | --- |
| 3a | S4 (live Embedded Signup, coexistence), S9 (Meta health), templates in the backoffice |
| 3b (postponed, section 4) | S7 (photos in the form and list), S6 (thumbnails), S3 (image messages) |
| 3c (done) | S7 ("Cargar desde un link", "Actualizar desde el link") |
| 4.1–4.4 | S6 (follow-ups and reminders), Configuración (Google Calendar), the weekly email |

## Daily routine

1. Write the work block's prompt from this file, one item per prompt.
2. Ask for the plan first and confirm it.
3. Review the diff, run the app, and try the "Done when" check yourself.
4. Commit with green CI and update this file with what moved.
