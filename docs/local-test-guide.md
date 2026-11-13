# Local test guide: inmo24x7 and Cuentas Claras (Days 1–9A)

Run these checks in order on a freshly seeded database. Each one says what to do and what
you should see. Days 1–7C cover inmo24x7; Day 8 adds Cuentas Claras next to it, on the same
platform, and Day 9A its WhatsApp reminders.

The steps follow the Day 1–9A prompts, plus the invitation-only accounts and the new look added
at the end of Day 8. If a final summary named something differently, the summary wins. The [Days 1–6 PDF](inmo24x7%20local%20test%20guide%20(Days%201–6).pdf) is
the older version of the first half.

---

## External accounts: what you need, and when

**Nothing external is needed to test locally.** Dev sign-in (passwords checked by the API), the
fake LLM, the fake WhatsApp sender ("log"), Mailpit and the local Postgres replace every
service.

The table lists every outside account the project uses, and the first moment you need it.

| Service | Needed for | Local testing | Real phone test | Production (go-live) | Where it's documented |
| --- | --- | --- | --- | --- | --- |
| **Docker, uv, Node 22.13+** | everything | **yes** | yes | yes (on the VM: Docker) | README, "Requirements" |
| **LLM provider** (Anthropic, OpenAI, DeepSeek, Kimi or MiMo): an API key | real agent replies | optional (fake model without it) | optional | **yes**, one provider | README, "A real model" |
| **Meta for Developers**: an app with WhatsApp; a test number; a permanent token | WhatsApp for real | no (`WHATSAPP_SENDER=log`) | **yes**: test app, your phone as test recipient | **yes**: Business portfolio, verified business, Tech Provider, Embedded Signup configuration, Live mode, template `confirmacion_visita` | go-live.md §8; README, "Testing WhatsApp locally" |
| **Tunnel** (cloudflared or ngrok, free) | Meta reaching your laptop | no | **yes** | no (the VM has a domain) | this guide, "From your phone" |
| **Supabase**: a project (free plan works) | sign-in (email and password, the reset email) and Postgres | no (`AUTH_MODE=dev`); optional `npx supabase start` | no | **yes**: Data API off, **sign-ups off**, SMTP, reset-password template, JWT keys, the **service-role key** for the APIs, session pooler | go-live.md §3 |
| **Domain + DNS** | HTTPS hosts | no | no | **yes**: `api.`, `app.`, `admin.`, optional `grafana.`; later the Cuentas Claras hosts | go-live.md §1 |
| **Oracle Cloud** (or any Linux VM with Docker): an ARM VM | running production | no | no | **yes**: VM, VCN rules for 80/443 | deploy/bootstrap.md |
| **Oracle Object Storage** (or any S3-compatible bucket) and an **age** key pair | encrypted daily backups | no (the rehearsal backs up to a local folder) | no | **yes** | deploy/restore.md |
| **SMTP provider** (Brevo, Resend, SES…) | invitation, new-lead and reconnect emails, Supabase's reset email, Grafana alerts | no (Mailpit) | no | **yes** | go-live.md §3.6 and §6 |
| **GitHub**: repository variables and secrets | building images (GHCR) and the optional deploy workflow | no | no | **yes**: until the variables exist, CI skips the image build | go-live.md §4 and §12 |
| **Sentry**: three projects | error reports, source maps, the backoffice's Errores page | optional (a test project, see Day 7C) | optional | recommended | go-live.md §12a |
| **LangSmith**: an API key | agent traces ("Ver traza") | optional | optional | optional | README, "A real model and LangSmith" |
| **Grafana, Loki, Alloy** | logs | optional, runs in Docker (no account) | — | on the VM (no account) | deploy/observability.md |
| **Mercado Pago** (Cuentas Claras) | payment links and payments | not yet: Day 9B | — | Day 9B+ | — |
| **A second Meta app** (Cuentas Claras) | its own webhook URL for reminders and replies | no (the seed's log-sender number) | its test number, for a real reminder | **yes**, at its go-live | go-live.md §8b |
| **ARCA** (Cuentas Claras) | reading invoices directly | not in the MVP (CSV import instead) | — | post-MVP | — |

**Summary:**

- **Local testing** needs no accounts at all.
- **Your own phone on WhatsApp** needs a Meta test app plus a tunnel.
- **Production** needs everything in the table except the optional rows.

---

## Before you start

1. **Check `.env`:**
   - It has `AUTH_MODE=dev`, `VITE_AUTH_MODE=dev` and `WHATSAPP_SENDER=log`.
   - Leave `LLM_MODEL` empty for the fake model, or set e.g. `LLM_MODEL=deepseek:deepseek-chat` with `DEEPSEEK_API_KEY` for real replies.
2. **Reset and seed both products:** `uv run --all-packages python scripts/seed_dev.py --reset --yes`
   - It prints every account, the password and the invitation links (copy them for "Accounts and invitations").
   - Optional, an empty Mailpit first: `curl -X DELETE http://localhost:8025/api/v1/messages`.
3. **Start everything:** `uv run --all-packages python scripts/dev.py`
   - It migrates with `alembic upgrade heads` and starts both products.
   - Use `--product inmo24x7` or `--product cuentas-claras` to run only one.
   - Add `--observability` for Grafana (Day 7C).
4. **Wait for the URLs** in the terminal, then open http://localhost:8001/health/ready and http://localhost:8002/health/ready.

| What | Address |
| --- | --- |
| inmo24x7 panel | http://localhost:5173 |
| inmo24x7 backoffice | http://localhost:5174 |
| inmo24x7 API docs | http://localhost:8001/docs |
| Cuentas Claras panel | http://localhost:5175 |
| Cuentas Claras backoffice | http://localhost:5176 |
| Cuentas Claras API docs | http://localhost:8002/docs |
| Mailpit (emails) | http://localhost:8025 |
| Grafana (with `--observability`) | http://localhost:3000 (admin / admin) |

Nobody can sign up: an admin creates every account ("Dar de alta un negocio"). One email is one
account with **one password for both products**, and a separate business in each.

**Accounts** (one per line: email, then password; copy the one you need):

Both products (backoffices 5174 and 5176, and the wizard in both panels):

```text
admin@local.test               local-1234
nuevo@local.test               temporal-1234
```

inmo24x7 (panel 5173):

```text
dueno@inmobiliariasur.test     local-1234
duena@palermoprop.test         local-1234
dueno@belgranohogar.test       local-1234
duena@caballitoinmuebles.test  local-1234
dueno@nortebienes.test         local-1234
invitada@villaurquiza.test     temporal-1234
```

Cuentas Claras (panel 5175):

```text
dueno@ascensoresdelta.test     local-1234
dueno@monitoreosur.test        local-1234
duena@soporteitnorte.test      local-1234
invitado@matafuegosnorte.test  temporal-1234
```

**Which account for which scenario: inmo24x7** (credentials first, then what to test):

- dueno@inmobiliariasur.test / local-1234: healthy business at 5173 (properties, leads, inbox, KPIs, WhatsApp "Conectado").
- duena@palermoprop.test / local-1234: WhatsApp "Verificación pendiente" (5173).
- dueno@belgranohogar.test / local-1234: onboarding stuck at "2 de 5" for 3 days, "Necesitan ayuda" (5173).
- duena@caballitoinmuebles.test / local-1234: WhatsApp "Acción requerida", Meta error 190 (5173).
- dueno@nortebienes.test / local-1234: suspended, "Tu cuenta está suspendida" (5173).
- nuevo@local.test / temporal-1234: forced password change, then the wizard ("Nuevo Inmo" at 5173, "Nuevo Negocio" at 5175).
- invitada@villaurquiza.test / temporal-1234: the invitation link from the seed output or Mailpit (5173).
- admin@local.test / local-1234: platform admin, inmo24x7 backoffice (5174).
- dueno@inmobiliariasur.test / local-1234 at 5174: "Solo administradores de la plataforma."
- dueno@ascensoresdelta.test / local-1234 at 5173: "Tu cuenta no está habilitada" (a Cuentas Claras owner).

**Which account for which scenario: Cuentas Claras:**

- dueno@ascensoresdelta.test / local-1234: 40 invoices and 25 clients; Inicio, Facturas, Clientes, the drawer, imports (5175).
- dueno@monitoreosur.test / local-1234: suspended, "Tu cuenta está suspendida" (5175).
- duena@soporteitnorte.test / local-1234: wizard unfinished, resumes at "Tus facturas"; no invoices, so Inicio shows the empty state after "Terminar después" (5175).
- invitado@matafuegosnorte.test / temporal-1234: invited, never came in; the invitation link ("Te invitaron a Cuentas Claras: Matafuegos Norte") or the forced change, then the wizard (5175).
- nuevo@local.test / temporal-1234 (or the password you chose in inmo24x7): the wizard for "Nuevo Negocio" (5175).
- admin@local.test / local-1234: platform admin, Cuentas Claras backoffice (5176): Negocios, Dar de alta, Detalle, Suspender/Reactivar.
- dueno@ascensoresdelta.test / local-1234 at 5176: "Solo administradores de la plataforma."
- dueno@inmobiliariasur.test / local-1234 at 5175: "Tu cuenta no está habilitada" (an inmo24x7 owner).

**Any product:**

- Any email, or a seeded one with a wrong password: "El email o la clave no son correctos."
- A new email (e.g. prueba1@local.test) / the temporary password the "Dar de alta" dialog shows once: a new owner.

A password you change during the tests stays until the next `seed_dev.py --reset --yes`.

**Checking the seeded accounts:**

- The seed prints the accounts and the invitation links when it runs.
- To list them from the database:

  ```bash
  psql postgresql://followup:followup@localhost:5433/followup \
    -c "SELECT email, must_change_password FROM accounts ORDER BY email;" \
    -c "SELECT email, product, is_platform_admin FROM profiles ORDER BY product, email;"
  ```

**Switching user:** sign out, or run `localStorage.clear(); location.reload();` in the browser console (F12 → Console). Each panel and backoffice runs on its own port, so each keeps its own session.

---

## Accounts and invitations (Day 8, both products)

Use private windows. inmo24x7 takes inmo24x7.com's look (night-blue gradient behind the sign-in
card, green-to-navy logo, green buttons, navy sidebar). Cuentas Claras takes naranjax.com's
colors (purple gradient, orange-to-purple logo, orange buttons, purple sidebar).

**Sign-in**

- [ ] http://localhost:5173 while signed out goes to `/ingreso`; so does http://localhost:5173/onboarding.
- [ ] Ingreso: email and **Clave**, "Entrar", "¿Olvidaste tu clave?", "Las cuentas las crea un administrador…", and the dev hint with `local-1234`. No Google, no magic link, no way to sign up.
- [ ] A wrong password, or an email with no account: "El email o la clave no son correctos."
- [ ] "¿Olvidaste tu clave?" in dev mode: "En modo desarrollo pedile a un admin una clave temporal nueva." (with Supabase it emails a reset link to `/cambiar-clave`).
- [ ] `dueno@inmobiliariasur.test` / `local-1234` lands on Inicio, no password change.
- [ ] The same account at the Cuentas Claras panel (http://localhost:5175): signs in, then "Tu cuenta no está habilitada" with "Cerrar sesión" (nobody invited it there). No wizard.

**Temporary password**

- [ ] `nuevo@local.test` / `temporal-1234` at http://localhost:5173: "Elegí tu clave" first. Typing http://localhost:5173/onboarding or `/` by hand comes back here.
- [ ] Two different passwords: "Las dos claves no coinciden."; fewer than 8 characters: "al menos 8 caracteres"; your email as password: "La clave no puede ser tu email."
- [ ] "Guardar mi clave" opens the wizard at step 2 "Tu agente", for "Nuevo Inmo" (the admin named it; step 1 is already done).
- [ ] Sign out, sign in with `temporal-1234`: refused. With the new password: back in the wizard.

**Invitation link**

- [ ] Mailpit (http://localhost:8025) has "Te invitaron a inmo24x7: Villa Urquiza Propiedades" (once `dev.py` is running; the worker sends it). It has the link and **no password**. The seed output prints the same link.
- [ ] The link opens "Bienvenido a inmo24x7" with the business and the email; choose a password → "Crear mi clave y entrar" → the wizard at step 2.
- [ ] Open the same link again: "Ya tenés tu clave" with "Ir a entrar".
- [ ] A link with a changed token: "Link no válido".

**Dar de alta un negocio** (both backoffices, as `admin@local.test`)

- [ ] inmo24x7 backoffice (5174) → "Dar de alta un negocio" with a new email (e.g. `prueba1@local.test`): the dialog shows "Te enviamos la invitación a…", the temporary password with "Copiar", and "Se muestra una sola vez". "Listo" opens the detail.
- [ ] Mailpit has the invitation email; the detail shows an "Invitación" card while the owner hasn't come in.
- [ ] "Reenviar invitación": a new email arrives, and the first link now says "Este link venció".
- [ ] "Generar clave temporal nueva": a new password shows once; the old one stops working.
- [ ] Sign in to the panel with the new email and that password: "Elegí tu clave", then the wizard. Back in the backoffice the "Invitación" card is gone, and Actividad shows "Negocio dado de alta", "Invitación enviada al dueño", "Invitación reenviada", "Clave temporal nueva" and "El dueño entró por primera vez".
- [ ] The same email again: "Ese email ya tiene un negocio en este producto."
- [ ] Cuentas Claras backoffice (5176) has the same "Dar de alta un negocio"; its email says "Te invitaron a Cuentas Claras".
- [ ] Inviting `dueno@inmobiliariasur.test` from the Cuentas Claras backoffice: no temporary password ("Ya tenía una cuenta en la plataforma: entra con su clave de siempre."); it signs in to 5175 with `local-1234`.

## Sign-in and onboarding (Days 1–2): inmo24x7

Continue as `nuevo@local.test` with the password you chose above (it has a business but has not set it up).

- [ ] The wizard resumes at step 2. Click step 1 "Tu negocio" in the stepper: "Nuevo Inmo" is prefilled; rename it and change the type. An existing name ("Inmobiliaria Sur") still works, with no error.
- [ ] Step 2, "Tu agente":
  - the greeting preview changes as you type the agent's name;
  - change the tone, disable a question, reorder two, add a custom one;
  - change team hours and the alert email.
- [ ] "Usar lo recomendado" resets the form without saving. "Guardar y probar mi agente" saves and opens step 3.
- [ ] "Terminar después", sign out, sign in again: the wizard reopens at the same step.
- [ ] Go back to step 2 from the stepper: your changes are still there.
- [ ] Finish steps 4 and 5. "Ir a mi panel" opens Inicio with the checklist.
- [ ] Agente: the same form, with "Versión N" and the history. Saving without changes doesn't create a version.
- [ ] Configuración: name and type, hours, alert emails and "Prueba · N días". They match step 2.

## Agent and simulator (Day 3)

Still as `nuevo@local.test`, in step 3 "Probalo" or at http://localhost:5173/probar.

With the fake model, use simple phrasing: "busco un 2 ambientes para alquilar en Palermo", "hasta 900 mil". Off-script questions only work with a real `LLM_MODEL`.

- [ ] The agent greets with its name and the business name.
- [ ] One question per message, in the configured order, skipping disabled ones.
- [ ] "Lo que el agente ya sabe" fills in as you answer. Unknown items say "Pendiente".
- [ ] Property cards appear (sample listings, "Está usando propiedades de ejemplo" banner).
- [ ] Ctrl+C on `dev.py`, start it again (no `--seed`), reload: the conversation is where you left it.
- [ ] "Reiniciar" starts a new conversation. A tone change shows "Cambiaste tu agente…" until you restart.

## Properties and leads (Day 4)

As `dueno@inmobiliariasur.test`. The files are in `docs/samples/`.

- [ ] Propiedades: seeded list with search, the operation filter and pagination.
- [ ] Import `propiedades.csv`: "Importamos 20 de 20". Import it again: nothing duplicated.
- [ ] Import `propiedades.xlsx`: same result.
- [ ] Import `propiedades-con-errores.csv`: 12 of 15, three Spanish errors, and "Descargar las 3 con errores" downloads only those rows.
- [ ] "Agregar una" creates a property; edit works; a paused one disappears from the agent's results.
- [ ] "Probar el agente": the cards are your own properties, with no sample banner.
- [ ] Visit slots: "me interesa la de Gorriti" gives two slot buttons inside team hours.
- [ ] Pick a slot, give a name and phone: "El agente derivó la consulta a tu equipo".
- [ ] "quiero hablar con una persona": immediate hand-off.
- [ ] Consultas shows simulator leads with the "Prueba" badge.

## WhatsApp without Meta (Day 5)

**How it works:** the script sends signed fake WhatsApp messages to the API, and the log sender "delivers" the replies.

**How to run it:**
- Use a second terminal and a number the seed doesn't use.
- Wait about 5 s between messages (the debounce is 3 s).

```bash
S="uv run --all-packages python scripts/simulate_whatsapp.py --from 5491166667777"
$S "Hola, busco un 2 ambientes para alquilar en Palermo"
$S "hasta 900 mil"
$S "Me interesa la primera"
$S --slot slot-YYYYMMDDHHMM "mié 4/11 10:00"   # the slot the agent offered: 4/11 10:00 → slot-202611041000
$S "Me llamo Ana"
$S --audio
```

- [ ] Inicio shows "Agente activo" with the seeded fake number.
- [ ] Three messages within 3 s get one answer.
- [ ] The lead appears in Consultas "por WhatsApp", with no "Prueba" badge.
- [ ] Replies go Enviado → Entregado → Leído.
- [ ] The agent never asks for a phone number.
- [ ] `--audio` gets "Por ahora solo puedo leer mensajes de texto. ¿Me lo escribís?".
- [ ] After the hand-off, the new-lead email is in Mailpit with a link that opens the lead.
- [ ] Restart `dev.py` mid-conversation: no message is lost.

## Inbox, takeover, visits and KPIs (Day 6)

As the owner. Use Ana's lead and keep `$S`.

- [ ] Inicio:
  - four KPI cards with this week's seeded data;
  - "Para atender hoy" opens leads in Consultas.
- [ ] Tabs:
  - "Para atender · N", "Visitas" and "Todas" are right;
  - search by name, zone ("Palermo") and phone in another format ("11 6666").
- [ ] "Exportar CSV" opens in Excel with proper columns and accents.
- [ ] "Tomar la conversación":
  - your reply goes Enviado → Entregado → Leído;
  - `$S "Perfecto, gracias"` appears within about 5 s and the agent stays quiet.
- [ ] "Devolver al agente", then `$S …`: the agent answers again without repeating questions.
- [ ] "Confirmar visita" with a new time:
  - status "Visita confirmada";
  - the lead leaves "Para atender";
  - Visitas agendadas goes up.
- [ ] "Cancelar visita" on another lead: back to "Pidió hablar con alguien".
- [ ] 24-hour rule: on the old seeded lead the reply box is disabled with the "Pasaron más de 24 horas…" explanation.

## WhatsApp connection, backoffice and suspension (Day 7)

**Embedded Signup locally**

- [ ] Configuración → WhatsApp: "Conectar WhatsApp" is disabled with "no está configurada en este entorno", because `VITE_META_APP_ID` is empty.
  - The real popup only runs on HTTPS with a Meta app; see "From your phone".
  - Locally, admins connect numbers by hand in the backoffice.

**Backoffice (http://localhost:5174)**

- [ ] As the owner: "Solo administradores de la plataforma." with "Cerrar sesión".
- [ ] Every backoffice page (both products) shows the admin's email and "Cerrar sesión" at the bottom of the sidebar (at the top on a phone); it signs out to the backoffice's sign-in.
- [ ] As `admin@local.test`, Negocios (S8):
  - four KPIs;
  - filters "Necesitan ayuda" and "En prueba";
  - search;
  - each row shows plan, onboarding "N de 5", the WhatsApp badge and leads in 7 days.
- [ ] "Dar de alta un negocio": see "Accounts and invitations" above (the owner gets a temporary password and an emailed link, and joins that business; no other one is created).
- [ ] Detalle (S9):
  - WhatsApp diagnosis with the WABA masked;
  - activity log, onboarding, plan usage, users.
- [ ] "Suspender" with a reason:
  - in the panel, that owner sees "Tu cuenta está suspendida";
  - "Reactivar" restores it;
  - both show in Actividad.
- [ ] "Enviarle link para reconectar": the email is in Mailpit.
- [ ] Salud del sistema shows jobs, webhooks, failed sends, version and database. Planes is read-only.
- [ ] Simulador / "Probar su agente" chats with any business's agent.

**Production rehearsal (optional)**

- [ ] Run `npx supabase start`, then `deploy/rehearsal/rehearsal.sh up`, then `deploy/rehearsal/rehearsal.sh smoke`. Every line should say `ok`, ending with "Rehearsal passed."
- [ ] Clean up with `deploy/rehearsal/rehearsal.sh down` and `npx supabase stop`.
- See `deploy/rehearsal.md`. It builds images locally and needs no GitHub variables.

## Errors, logs and LLM cost (Day 7C)

- [ ] **Reference code:** any unexpected error in a panel ends with "Código de referencia: xxxxxxxx".
- [ ] **Logs:**
  - start with `dev.py --observability`;
  - open Grafana (http://localhost:3000, admin/admin) → Dashboards → *inmo24x7 — operación*, environment `development`;
  - API lines appear;
  - Explore `{environment="development"} | json | tenant_id="<id>"` finds one business's lines.
- [ ] **Errores page:**
  - Backoffice → Errores without Sentry settings shows "Sentry no está configurado…";
  - "Enviar errores de prueba" answers with a reference code and says the panel has no DSN.
- [ ] **Sentry for real (optional):**
  - set `SENTRY_DSN` and `VITE_SENTRY_DSN` to a test project's, and restart;
  - "Enviar errores de prueba" creates `SentryTestError` and "Error de prueba del panel" in Sentry within a minute.
- [ ] **Consumo:**
  - chat in the simulator, then Backoffice → Consumo shows the business, calls, conversations and the daily chart;
  - with the fake model: tokens 0 and "sin datos";
  - with a real model whose price is missing from `followup_platform/billing/llm_prices.toml`: tokens counted, cost "—" and "sin precio";
  - after adding the price, `scripts/recompute_llm_costs.py --from <date> --apply` fills in the costs;
  - "Exportar CSV" works.

## Cuentas Claras: invoices and clients (Day 8)

The sample files are in `docs/samples/cuentas-claras/`. Its README gives the reference date the due dates are relative to.

**Wizard**: private window, http://localhost:5175, `nuevo@local.test` with **the password you chose in inmo24x7** (one account for both products: no second password change). It was invited to "Nuevo Negocio".

- [ ] Ingreso shows "Cuentas Claras", "Cobrá sin reclamar." in its own colors: purple background, orange "Entrar" button, orange-to-purple "C" logo.
- [ ] Signing in opens the wizard at step 2 "Tus facturas" (the admin created the business).
- [ ] Step 1 "Tu negocio" (from the stepper): "Nuevo Negocio" prefilled, and the five service types (Mantenimiento, Seguridad y monitoreo, Soporte IT, Agencia con abonos, Otro servicio mensual).
- [ ] Step 2 "Tus facturas":
  - "Descargar la plantilla" downloads the template;
  - importing `facturas.csv` shows "Importamos 40 de 40" and the button becomes "Seguir";
  - or "Cargar después" without importing.
- [ ] Step 3 "Recordatorios": the read-only sequence (3 días antes, el día del vencimiento, 3 días después, 7 días después) and "Muy pronto vas a poder ajustarla.".
- [ ] Step 4 "Conectar": WhatsApp and Mercado Pago marked "Muy pronto".
- [ ] Step 5 "Listo" opens Inicio.
- [ ] "Terminar después", sign out and in: the wizard resumes at the same step.

**Inicio**

- [ ] The checklist: cuenta and facturas done; WhatsApp, Mercado Pago and recordatorios pending.
- [ ] "Total a cobrar" and "Vencido" cards, with "N facturas".
- [ ] With no invoices (duena@soporteitnorte.test / local-1234, after "Terminar después"): the empty state and "Importar facturas".

**Facturas (C2)**: as `dueno@ascensoresdelta.test`.

- [ ] Tabs "Pendientes (32)", "Vencidas (13)", "Prometidas (0)" (until Day 9) and "Pagadas este mes", each with its count. The sample's 8 paid invoices are paid in the month before the reference date, so "Pagadas este mes" starts at 0 early in the month; marking one as paid (below) adds it.
- [ ] Columns:
  - client with the subtitle under it;
  - number like "B 0003-00001245";
  - amount in es-AR format;
  - due date ("10 oct");
  - status badge ("Vencida · N días", "Por vencer", "Pendiente", "Pagada · …");
  - "Lo próximo" shows "—".
- [ ] Search by client, by CUIT digits, and by number in three formats ("1245", "0003-00001245", "B 3-1245").
- [ ] Pagination "Mostrando 1 a 25 de N", and the ARCA notice.
- [ ] A row opens the drawer:
  - invoice, client, payment;
  - "Marcar como pagada" (date, method, reference) moves it to "Pagadas este mes";
  - "Anular" asks for a reason.
- [ ] Import `facturas-con-errores.csv`:
  - "Fila 7: el CUIT no es válido.";
  - "Fila 12: falta el vencimiento.";
  - "Fila 20: la fecha tiene que ser dd/mm/aaaa.";
  - "Fila 31: el monto no es un número.";
  - the warning "la factura ya figuraba pagada; no la cambiamos.";
  - the error download contains only the failed rows, with an `error` column.
- [ ] Import `facturas.csv` again: invoices are updated, not duplicated, and paid ones stay paid.
- [ ] `facturas.xlsx` gives the same result as the CSV.

**Clientes**

- [ ] The companies created by the import, each with its open invoices and amount owed.
- [ ] The "Sin WhatsApp" filter and badge.
- [ ] Search by name or CUIT.
- [ ] New client: an invalid CUIT (e.g. 20-12345678-0) shows the error before saving; a valid one (e.g. `30712345671`) saves and is shown as `30-71234567-1`. A WhatsApp number without an area code is refused too.
- [ ] Client detail lists its invoices.

**Configuración**

- [ ] Business name and type, team hours and notification emails save and reload.

**Two products, one account**

- [ ] `nuevo@local.test` has one password and a different business in each panel: "Nuevo Inmo" at 5173, "Nuevo Negocio" at 5175. Neither shows the other's data.
- [ ] Owners of each product are separate: `dueno@inmobiliariasur.test` gets "Tu cuenta no está habilitada" at 5175, and `dueno@ascensoresdelta.test` gets it at 5173.
- [ ] Cuentas Claras backoffice (5176, `admin@local.test`):
  - Negocios lists only Cuentas Claras businesses (Ascensores Delta, Monitoreo Sur, Soporte IT Norte, Nuevo Negocio, Matafuegos Norte), with owner, plan, onboarding "N de 5", clients, open amount, alta;
  - Matafuegos Norte and Nuevo Negocio say "todavía no entró" and show the "Invitación" card;
  - detail shows the checklist, activity and Suspender/Reactivar;
  - Monitoreo Sur is "Suspendido" with its reason; dueno@monitoreosur.test sees "Tu cuenta está suspendida" at 5175 until "Reactivar".
- [ ] The inmo24x7 backoffice (5174) doesn't list Ascensores Delta.

---

## Cuentas Claras: WhatsApp and reminders (Day 9A)

The seed gives Ascensores Delta a fake WhatsApp number (`dev-cc-phone-1`, log sender: nothing
reaches Meta), its four templates already approved, the default policy saved and transfer
details. Reminders go out only Monday to Friday, inside the send window (default: mornings
9–12, Buenos Aires), never on national holidays.

**C4, Recordatorios y cobros** (5175, `dueno@ascensoresdelta.test`):

- [ ] The new nav item opens C4: four steps (3 días antes, el día del vencimiento, 7 días después, 15 días después: avisar al dueño), each reminder with its text and "aprobada"; the escalation says no more messages and an email to you.
- [ ] "+ Agregar un paso" adds one (e.g. 10 días después); two steps on the same day: "Dos pasos no pueden caer el mismo día." without saving. "Guardar cambios" → "Guardamos los cambios.".
- [ ] Horario de envío: the four presets; Personalizado shows "De … a …" (06:00–22:00).
- [ ] "No enviar en feriados" lists the next holidays (e.g. 23 nov, 7 dic, 8 dic); "Pausar si el cliente prometió pagar" is on.
- [ ] Mensajes: four texts with sample values; "Editar texto" → change one → "Enviar a revisión de Meta": the card says "aprobada" still with "Hay una versión nueva en revisión" only if Meta has not approved it yet (locally it is approved at once). A field at the start (`{cliente} hola`) → "Revisá el texto: …".
- [ ] WhatsApp: the number, "Este mes: N mensajes de recordatorio" (no "respuestas gratis" text). Mercado Pago: "Muy pronto".

**Seeing a reminder go out:**

1. In C4 choose Personalizado 06:00–22:00 (any weekday hour then works) and save. Saving plans the business again.
2. Within a few seconds the worker logs `reminders_planned` and one `whatsapp_log_send` per client (at most one per client and day); log statuses follow (sent → delivered → read).
3. Facturas → "Lo próximo": "Recordatorio el dd/mm 9:00" for the next step, "Sin WhatsApp" for clients without a number, "Escalado al dueño" for invoices past 15 days that already got their last reminder. Mailpit (8025) has "Escalar al dueño: N facturas sin pagar" on the next planning.
4. The payment link of the last reminder:
   ```bash
   docker compose exec db psql -U followup -tAc "SELECT body->'template'->'components'->1->'parameters'->0->>'text' FROM whatsapp_outbound ORDER BY updated_at DESC LIMIT 1"
   ```
   Open http://localhost:5175/p/<token> in a private window (no login): Ascensores Delta, "Para <cliente>", the invoices with due date and amount, the total, "Pronto vas a poder pagar con Mercado Pago" (disabled) and the transfer details. No CUIT, no email. `http://localhost:5175/p/xxx` → "Este link ya no está disponible".
5. Backoffice (5176) → Ascensores Delta → Recordatorios: the four templates "aprobada", "N enviados este mes", "Últimos que no salieron" (e.g. "La plantilla no está aprobada"), and **Planificar ahora** ("Listo: N envíos programados…" or why nothing went out). Below, the WhatsApp manual connection (the same panel as inmo24x7's, without the visit template).

**Promises, opt-out and replies:**

- [ ] Facturas → an overdue invoice → "Registrar promesa de pago" with a date: status "Con promesa · hasta dd/mm", "Lo próximo: Pausado: promesa hasta dd/mm", tab "Con promesa" counts it. "Quitar promesa" brings back the sequence.
- [ ] Clientes → a client → "No enviar recordatorios": its invoices say "Sin recordatorios (pedido del cliente)".
- [ ] A reply (Clínica San Martín's number in the sample):
  ```bash
  uv run --all-packages python scripts/simulate_whatsapp.py --product cuentas-claras --from 5491155550106 "Ya la pagué ayer"
  ```
  Mailpit: "Respondió: “Ya la pagué ayer” (Clínica San Martín)" with a link to the client. Nobody answers on WhatsApp (Day 10).
- [ ] A rejected template: take a `meta_template_id` from `cc_whatsapp_templates` and run `scripts/simulate_whatsapp.py --product cuentas-claras --template-status <id> REJECTED --reason INVALID_FORMAT`: C4 shows "rechazada: el formato no es válido", and that step's invoices say "En espera: plantilla en revisión".

**Onboarding and Configuración:**

- [ ] `nuevo@local.test` at 5175, wizard step "Recordatorios": the same editor (short), "Guardar y seguir" saves it and goes to "Conectar"; Inicio's checklist then has "Configurar los recordatorios" done.
- [ ] "Conectar": WhatsApp's three steps and "Conectar WhatsApp" (disabled without `VITE_CUENTAS_CLARAS_META_*`: "La conexión con Meta no está configurada en este entorno…"), Mercado Pago "Muy pronto".
- [ ] Configuración: the WhatsApp section (`/configuracion#whatsapp`, where the reconnect email links) and "Datos para transferencia" (an invalid CBU → "Revisá los datos…"; both empty removes them).
- [ ] inmo24x7 is unchanged: its WhatsApp screens (S4, Configuración, backoffice S9) look and behave as on Day 7.

---

## Automated tests

Postgres must be up (`docker compose up -d --wait db`). Then:

```bash
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run alembic upgrade heads
uv run --all-packages pytest
uv run --all-packages python scripts/generate_types.py && git diff --exit-code -- packages/api-client-*/src/schema.ts
corepack pnpm lint && corepack pnpm typecheck && corepack pnpm test
```

Everything must be green before you commit. The tests use their own database (`followup_test`) and never touch your dev data.

## From your phone (real WhatsApp, inmo24x7)

This needs:
- the Meta test app, with your phone added as a test recipient;
- a permanent token;
- a tunnel.

**Steps:**

1. In `.env`, set `WHATSAPP_SENDER=cloud`, `META_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` and `TOKEN_ENCRYPTION_KEY`, then restart `dev.py`.
2. Start a tunnel: `cloudflared tunnel --url http://localhost:8001` (or `ngrok http 8001`).
3. In the Meta app, WhatsApp → Configuration:
   - callback `https://<tunnel>/webhooks/whatsapp`, with your verify token;
   - "Verify and save";
   - subscribe to `messages`.
4. In the backoffice, for Inmobiliaria Sur:
   - enter the phone number ID, WABA ID and token;
   - "Probar conexión" → "Suscribir la app" → "Enviar mensaje de prueba".
5. Write to the test number from your phone and repeat the Day 5–6 checks. Visit slots arrive as tappable buttons.

**Things to know:**

- **Tunnel URL:** the Cloudflare quick tunnel changes URL on every restart, so redo step 3 each time.
- **Embedded Signup:** testing it needs the panel on HTTPS (a tunnel to 5173) and the `VITE_META_*` values.
- **Cuentas Claras:** the same, with its own Meta app and API (8002): set the
  `CUENTAS_CLARAS_META_*` values, tunnel to 8002, subscribe `messages`, `account_update` and
  `message_template_status_update`, connect the number from its backoffice (5176) and add a
  client whose WhatsApp is your phone, with an invoice due in 3 days. "Planificar ahora"
  sends the reminder (once Meta approves the templates, usually minutes).

## Production: configuring the apps and handling passwords

The step-by-step is `docs/go-live.md` (and `deploy/bootstrap.md` for the VM). This is the map:
where each setting lives, and how to treat every password and key.

**Where configuration lives (three places, never the repository)**

| Place | What goes there | Who reads it | Secret? |
| --- | --- | --- | --- |
| `/opt/inmo24x7/.env.production` on the VM (from `deploy/.env.production.example`, `chmod 600`) | everything the APIs, workers, Caddy and backups need at runtime: database, Supabase server keys, LLM key, Meta secrets, SMTP, backup keys, Sentry, domains | Docker Compose, at `./deploy.sh` | **yes**: the only copy on the server |
| GitHub → Settings → Secrets and variables → Actions | **variables**: public values baked into the panels at build time (`INMO24X7_API_URL`, `INMO24X7_PANEL_URL`, `CUENTAS_CLARAS_API_URL`, `CUENTAS_CLARAS_PANEL_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `META_APP_ID`, `META_EMBEDDED_SIGNUP_CONFIG_ID`, Sentry DSNs); **secrets**: `SENTRY_AUTH_TOKEN`, `DEPLOY_SSH_KEY`, `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KNOWN_HOSTS` | CI, when it builds images and deploys | variables: no (anyone with the panel can read them); secrets: yes |
| The services' own dashboards | Supabase (sign-ups off, redirect URLs, SMTP, reset template), Meta (webhook URL and verify token), DNS, Oracle, Sentry | those services | the dashboard logins: yes |

Anything with `VITE_` or in a GitHub **variable** ends up in the JavaScript every visitor
downloads: only public values there, never a key that grants access.

**Every secret, where it comes from, where it goes**

| Secret | From | Goes in | Never in | If it leaks |
| --- | --- | --- | --- | --- |
| Database password (`DATABASE_URL`) | Supabase → Database settings | `.env.production` | GitHub, panels, chat | reset it in Supabase, update `.env.production`, `./deploy.sh <same sha>` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → API Keys (secret / service role) | `.env.production` only | panels, GitHub variables, logs | rotate in Supabase (new secret key, revoke the old), update the file, redeploy |
| `SUPABASE_ANON_KEY` | Supabase → API Keys (anon / publishable) | GitHub variable (panel builds) | — (public by design; the Data API is off and every table has RLS) | nothing to do; rotating means rebuilding the panels |
| `ANTHROPIC_API_KEY` (or the chosen provider's) | the provider's console | `.env.production` | GitHub, panels | revoke at the provider, new key, redeploy; set a spending limit there |
| `META_APP_SECRET` | Meta app → App settings → Basic | `.env.production` | panels, GitHub | "Reset" in Meta, update, redeploy |
| `WHATSAPP_VERIFY_TOKEN` | you invent it (long random) | `.env.production` and Meta's webhook form | — | change both places |
| WhatsApp access tokens of each business | Embedded Signup or the backoffice form | the database, **encrypted** with `TOKEN_ENCRYPTION_KEY` | anywhere else; the API never returns them | the business reconnects ("Enviarle link para reconectar") |
| `TOKEN_ENCRYPTION_KEY` | you generate it once (command in the example file) | `.env.production` **and** your password manager | anywhere else | **losing it** means every stored WhatsApp token is unreadable: keep the copy |
| `SMTP_PASSWORD` | the email provider | `.env.production`; the same SMTP in Supabase's dashboard | panels, GitHub | rotate at the provider, update both, redeploy |
| `RCLONE_S3_*` (backup bucket) | Oracle → Customer secret keys | `.env.production` | anywhere else | delete the key pair in Oracle, create a new one |
| age **private** key (backups) | `age-keygen` on your machine | your password manager and an offline copy; **never on the VM** | the VM, GitHub, email | without it no backup can be restored; test `deploy/restore.md` once |
| `GRAFANA_ADMIN_PASSWORD` | you invent it | `.env.production`; change it again at first login | — | change it in Grafana |
| `SENTRY_API_TOKEN`, `SENTRY_AUTH_TOKEN` | Sentry (read-only internal integration; release token) | `.env.production`; GitHub **secret** | panels | revoke in Sentry, new token |
| `DEPLOY_SSH_KEY` | a dedicated key pair for CI | GitHub **secret**; its public half in the VM's `authorized_keys` | your personal keys | remove it from `authorized_keys`, new pair |

**Rules for all of them**

- Your **password manager** is the source of truth. `.env.production` is a copy of it on the VM; nothing lives only on the VM.
- Never commit a real value: `.env`, `.env.production` and `deploy/rehearsal/.env.rehearsal` are git-ignored; only the `*.example` files are tracked.
- Never paste a key in chat, email, a ticket, a screenshot or a log. If it happens, treat it as leaked and rotate it.
- Development and production never share a key: local uses `AUTH_MODE=dev`, Mailpit, the log sender and the fake model.
- After changing any value in `.env.production`: `./deploy.sh <same sha>` (idempotent). After changing a GitHub **variable**: let CI build new images, then deploy them.
- Rotate when someone with access leaves, after any suspected leak, and at least once a year for the service-role key, the LLM key and the SMTP password.

**People's accounts in production**

- Supabase: **"Allow new users to sign up" off**, minimum password length 8, the reset-password email template in Spanish, your own SMTP (go-live §3).
- The first admin: `./dc.sh run --rm api python scripts/make_admin.py <you> --create` in `/opt/inmo24x7` on the VM (go-live §9). It prints a temporary password once; sign in to the backoffice and choose your own.
- Each customer: backoffice → "Dar de alta un negocio". Give them the temporary password through **another channel** than the email (WhatsApp, phone); the invitation email carries only the link. Either way they must choose their own password first.
- Lost password: "¿Olvidaste tu clave?" on the sign-in page (Supabase's reset email). An owner who never came in: "Generar clave temporal nueva" or "Reenviar invitación" in the backoffice.
- One person, one account: never share an admin login. To remove someone's access, delete the user in Supabase → Authentication → Users (and suspend the business if it's a customer leaving).
- Nobody, admins included, can see a user's password: Supabase stores only hashes, and temporary passwords are shown once and never stored in clear.

**Turning on Cuentas Claras in production** (same VM, database and Supabase project)

1. DNS A records for `cuentasclaras.`, `cuentasclaras-admin.` and `cuentasclaras-api.<domain>`.
2. In `.env.production`: the `CC_*` domains, `CUENTAS_CLARAS_CORS_ORIGINS`, `CUENTAS_CLARAS_PANEL_URL`, `CUENTAS_CLARAS_EMAIL_FROM`, and `cuentas-claras` added to `COMPOSE_PROFILES`.
3. GitHub variables `CUENTAS_CLARAS_API_URL` and `CUENTAS_CLARAS_PANEL_URL` (CI then builds its three images).
4. Supabase redirect URLs: add the two Cuentas Claras hosts with `/**`.
5. `./deploy.sh <sha>`, then `make_admin.py <you> --product cuentas-claras --create`.

## If something fails

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Blank white page | Supabase client with empty settings | F12 → Console; check `VITE_AUTH_MODE=dev`, restart `dev.py` |
| No dev hint (`local-1234`) on Ingreso | `.env` changed without a restart | Restart `dev.py` (Vite reads `.env` at start) |
| "El email o la clave no son correctos." with a seeded account | Database seeded before passwords existed, or a typo | `seed_dev.py --reset --yes`; passwords are `local-1234` / `temporal-1234` |
| "Tu cuenta no está habilitada" | Nobody invited that email to this product | Backoffice → "Dar de alta un negocio" with that email |
| No invitation email in Mailpit | The worker is not running | Look for the worker in the `dev.py` output; the job sends it within seconds |
| "Solo administradores" | Signed in as a non-admin | Sign in as `admin@local.test`, or `scripts/make_admin.py <email> --product …` (`--create` for a brand-new admin) |
| 401, or sent back to sign-in | API not in dev mode | `AUTH_MODE=dev`, restart |
| Errors about migrations or missing columns | Database behind the code | `uv run alembic upgrade heads` (note: **heads**) or `seed_dev.py --reset --yes` |
| Agent never answers WhatsApp | Worker not running, or the conversation is taken over | Look for the worker in the `dev.py` output; check the lead's state |
| "Tu agente no pudo responder ahora." | Real LLM failing (key, balance, model id) | Read the API error, or empty `LLM_MODEL` |
| No email in Mailpit | Simulator lead, or no hand-off yet | Emails are for WhatsApp leads, at hand-off or 15 minutes after the first message |
| Consumo shows "—" / "sin precio" | Model without a price | Add it to `llm_prices.toml`, then run the recompute script |
| Port already in use | Another `dev.py`, or the rehearsal | Stop it; `--product` runs only one product |
| Odd data after many tests | Leftovers | `scripts/seed_dev.py --reset --yes` |

When a check fails, note:
- the step;
- what you expected and what you saw;
- any red error from the browser console or the `dev.py` terminal.
