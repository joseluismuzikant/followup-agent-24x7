# OpenCode prompts — followup-agent-24x7

Two prompts, run in order, each in its own OpenCode session.

1. **Prompt 1** aligns the docs with the screens (docs only, no code). It also commits a written
   screen spec, because the galleries in `docs/*.html` are compressed bundles that a coding agent
   cannot read reliably.
2. **Prompt 2** is the next real step: Day 1 of the revised roadmap.

After Prompt 1, write each later day's prompt the same way as Prompt 2: copy the day's section
from the roadmap, add the matching screens from `docs/screens-spec.md`, and keep "plan first".

---

## Prompt 1 — Align the roadmap with the screens (docs only)

```text
You are working in the followup-agent-24x7 monorepo. Read README.md, ARCHITECTURE.md and
docs/roadmap-mvp-10-days.md first. This task changes documentation only: do not touch code.

CONTEXT
The prototype galleries docs/inmo24-screens.html and docs/cuentas-claras-screens.html are
compressed bundles; do not try to unpack them. Their full content is transcribed below. The
roadmap covers the happy path of each screen but misses a lot of what the screens show.

TASK
1. Create docs/screens-spec.md: one section per screen below, with three parts each:
   "What the user sees", "What must work" (behaviour, API, data) and "Roadmap day".
   UI copy stays in Spanish exactly as listed; everything else in English.
2. Rewrite docs/roadmap-mvp-10-days.md into docs/roadmap-mvp.md (git mv, keep history) using
   the revised day plan below. Keep the existing structure (Assumptions, MVP definition, lead
   time table, per-day "Done when", checkpoints, risks, daily routine). Every screen element in
   the spec must map to a day or to an explicit "Post-MVP" list. Nothing may be silently dropped.
3. Update the README link to the roadmap and the "Status" notes that are now stale.
4. Show me the plan (file outline + the revised day list) and WAIT for my OK before writing.

SCREENS — inmo24x7
S1 Ingreso: hero copy; "Continuar con Google"; email + "Enviarme un link para entrar" (magic
   link); links to Términos and Política de privacidad (pages do not exist yet).
S2 Onboarding, 5 steps with progress (Tu negocio, Tu agente, Probalo, WhatsApp, Listo),
   "Terminar después" (resume later). Only step 2 is mocked:
   agent name (default "Sofía", preview «Hola, soy Sofía, de Inmobiliaria Sur»); tone
   Cercano/Profesional/Formal; editable list of qualification questions (comprar o alquilar,
   zona, presupuesto, crédito hipotecario aprobado, cantidad de ambientes, "+ Agregar una
   pregunta"); team hours presets (L-V 9-18, L-S 9-13); lead notification email; after hours
   the agent keeps answering and proposes a visit for the team to confirm; "Usar lo
   recomendado", "Guardar y probar mi agente". Steps 1 and 5 are not mocked.
S3 Probalo (simulator): chat with agent header and "Reiniciar"; agent shows property cards
   (title, address, price, "Ver fotos", note when over budget); side panel "Lo que el agente
   ya sabe" with operation, zone, budget, rooms, name, contact (Pendiente until known);
   banner "Está usando propiedades de ejemplo" + "Subir mis propiedades"; buttons
   "Ajustar el agente" and "Me gusta, conectar WhatsApp".
S4 Conectar WhatsApp: 3 explained steps; "Conectar WhatsApp" (Meta Embedded Signup); help link
   for creating a business Facebook account; "Hacerlo más tarde y seguir probando";
   connection status card (Cuenta de Meta, Número verificado, Recepción de mensajes, Mensaje de
   prueba); "Pendiente en Meta" (verify business, add payment method) with links; Meta errors
   translated to Spanish (example: number already registered in another account).
S5 Panel Inicio: sidebar Inicio, Consultas, Propiedades, Agente, Configuración; badge "Agente
   activo" + WhatsApp number; "Probar el agente"; setup checklist "3 de 5 listos" (cuenta,
   agente, WhatsApp, propiedades, verificar empresa en Meta); KPIs for this week: consultas
   recibidas (+ how many out of hours), calificadas (with zone and budget), visitas agendadas,
   respuesta promedio; table "Para atender hoy" (name or phone, what they look for, status,
   age). Statuses: Calificando, Visita propuesta, Pidió hablar con alguien, Visita confirmada.
S6 Panel Consultas: tabs "Para atender · N", "Visitas", "Todas"; search by name, zone or phone;
   "Exportar CSV"; detail pane: name, phone, channel; "Tomar la conversación" (human takeover:
   the agent pauses and the team replies from the panel); "Confirmar visita" (sends the
   confirmation to the lead); visit card (address, day and time, awaiting confirmation);
   qualification data (incl. Garantía); full transcript; system events ("El agente derivó la
   consulta a tu equipo").
S7 Panel Propiedades: "Agregar una" (manual create), "Importar CSV o Excel"; import report
   "Importamos 42 de 45" + "Descargar las 3 con errores" + row-level errors in Spanish;
   search by address or zone; operation filter; columns title + address + listing link,
   operation, zone, price (ARS or USD), rooms, status Publicada/Pausada, inquiries per
   property; pagination. The agent only shows published properties with their real links.
S8 Backoffice Negocios (admins only): nav Negocios, Conversaciones, Simulador, Salud del
   sistema, Planes; "Dar de alta un negocio"; KPIs activos, en prueba, onboarding sin
   terminar, WhatsApp con problemas; search by name or email; filters Todos, Necesitan ayuda,
   En prueba; columns name + owner email, plan (Pro / Prueba · N días), onboarding N de 5,
   WhatsApp status (Conectado, Verificación pendiente, Acción requerida, Sin conectar),
   inquiries last 7 days, sign-up date.
S9 Backoffice Detalle del negocio: plan, sign-up date, owner; "Probar su agente", "Suspender";
   WhatsApp connection health with plain-language diagnosis, since when messages fail and the
   Meta error code (example: 190, permission revoked) + technical detail; number, WABA, business
   verification, last message received; "Enviarle link para reconectar", "Reintentar
   configuración", "Enviar mensaje de prueba"; activity log (system and user events with actor
   and time); onboarding checklist; plan usage (conversations this month N of 1.000, users);
   users with roles (dueño, agente).

SCREENS — Cuentas Claras
C1 Panel Inicio: nav Inicio, Facturas, Aprobaciones (count badge), Clientes, Recordatorios y
   cobros; status "Cobrando en automático · WhatsApp y Mercado Pago conectados"; "Importar
   facturas"; KPIs recuperado este mes, total a cobrar (N facturas), vencido (N facturas),
   promesas de pago (N clientes, before date); aging buckets (todavía no vence, 1-15, 16-30,
   más de 30 días); "Necesita tu atención" list (promise to approve, payment to verify,
   installment plan to approve); today's activity (reminders sent, paid with link, replied
   with a question) and next send time.
C2 Facturas: "Descargar plantilla CSV", "Importar facturas"; tabs with counts Pendientes,
   Vencidas, Con promesa, Pagadas este mes; search by client or invoice number; columns
   client + subtitle, invoice number (B 0003-00001245), amount, due date, status (Promesa por
   aprobar, Pago para verificar, Vencida · N días, Por vencer, Pagada · Mercado Pago) and
   "Lo próximo" (next scheduled action, e.g. "Recordatorio mañana 9:30"); pagination; notice
   that ARCA import is coming.
C3 Aprobaciones: three card types, each with the client's literal message and a preview of
   what the agent will answer. Promesa de pago: "Aprobar 5 nov", "Proponer otra fecha",
   "Responder yo". Plan de cuotas: schedule of installments; "Aprobar 3 cuotas", "Ofrecer 2
   cuotas", "Rechazar". Pago para verificar: receipt image sent by WhatsApp (tap to enlarge),
   note when the payment is not found in Mercado Pago; "Confirmar que pagó", "Pedir otro
   comprobante". After a decision, the agent continues the conversation.
C4 Recordatorios y cobros: editable sequence of steps (3 days before, due date, 7 days after),
   each with its WhatsApp template text and Meta status (aprobada / en revisión); last step at
   15 days stops messaging and notifies the owner; "+ Agregar un paso"; send window presets;
   "No enviar en feriados" (Argentine holidays); "Pausar si el cliente prometió pagar";
   Mercado Pago connected account + "Cambiar cuenta" (each business connects ITS OWN account;
   payments must go there); WhatsApp number + usage "1.000 respuestas gratis por mes; vas
   usando 214"; "Guardar cambios".
C5 Backoffice Negocios y envíos: nav Negocios y envíos, Conversaciones, Plantillas de WhatsApp,
   Simulador, Planes; KPIs recordatorios enviados, envíos fallidos, pagos registrados,
   plantillas en revisión; failed sends list with reason and action (number has no WhatsApp →
   avisar al negocio; Meta paused template for low quality → revisar plantilla; Mercado Pago
   webhook invalid signature → ver detalle) and "Reintentar todos"; tenants table with plan by
   managed clients (Hasta 50 / Hasta 150 / Prueba · N días), managed clients, recovered this
   month, WhatsApp status, Mercado Pago status.
Not mocked but in the nav: inmo24x7 Agente and Configuración, Cuentas Claras Clientes.
Add a short spec for each, derived from the related screens.

REVISED DAY PLAN (use this; adjust only if you find a dependency problem, and tell me)
Note: the Day 1 review fixes are already merged (CI default branch, single Alembic config,
production migrations, VITE_API_URL, migration-based fixture, Node engine, diagram). Remove them.
Day 1  Identity (Supabase JWT port, roles owner/manager/agent/viewer, admin flag, tenant scoping,
       sign-up use case with trial plan) + web app shell (router, auth guard, sidebar from S5)
       + S1 Ingreso + admin-only backoffice.
Day 2  S2 full 5-step wizard with resume; agent config stored in Tenancy and versioned;
       qualification questions are DATA the graph reads, not hard-coded; checklist on S5;
       Agente screen (edit the same config after onboarding).
Day 3  Conversation runtime (AgentRuntime port, LangGraph, Postgres checkpointer, fake LLM) +
       S3 simulator incl. "Lo que el agente ya sabe" (graph state exposed by the API), Reiniciar,
       sample properties seeded per tenant until they import their own; simulator also in S8.
Day 4  Properties S7 (CSV and XLSX import, error file download, manual create/edit,
       publish/pause, inquiries count) + Leads agent driven by the configured questions, with
       tools search properties, save contact, propose visit (slots inside team hours), hand
       off; lead statuses from S5.
Day 5  WhatsApp messaging (as before) + new-lead email; a Meta template for messages outside
       the 24-hour window (needed to confirm a visit later).
Day 6  S6 Consultas inbox: transcript, takeover (pause agent per thread, human replies sent
       through WhatsApp), confirm visit, tabs, search, CSV export; S5 KPIs (out of hours,
       average first-response time, visits booked).
Day 7  S4 Embedded Signup + connection health (store Meta error codes, detect revoked tokens
       and failing webhooks) + S8/S9 backoffice parity (KPIs, filters, detail, activity log from
       an audit log in Tenancy, plan usage, users, suspend, reconnect link, manual connect
       fallback) + deploy + backups + demo. inmo24x7 MVP demo-ready.
Day 8  Cuentas Claras skeleton; Clientes; C2 Facturas with CSV template and import report.
Day 9  Scheduling + C4: editable sequence, send window, holidays, pause on promise, escalation
       to owner; templates per tenant with Meta status sync; Mercado Pago OAuth per tenant,
       payment link per invoice, payment webhook marks paid and cancels reminders.
Day 10 Collections agent + C3: promise, installment plan, payment verification with the
       receipt media downloaded from WhatsApp and stored; counter-offers; "Responder yo"
       (reuses the takeover from Day 6).
Day 11 C1 dashboard (aging, attention list, activity, next send) + C5 backoffice (failed sends
       with retry, template health, Mercado Pago webhook health) + deploy.
Day 12 Hardening, monitoring and alerts, fresh-account stopwatch test of both products,
       landings, pilot kit. Cuentas Claras MVP demo-ready.
Post-MVP keeps the existing list, plus: Términos/Privacidad pages content, "Planes" admin
screens beyond a read-only plan, Conversaciones cross-tenant viewer if it does not fit Day 7.

LEAD TIME TABLE — add rows
- Mercado Pago OAuth application (redirect URL on the production domain) so each business
  connects its own account.
- WhatsApp template for visit confirmation / follow-up outside the 24-hour window (inmo24x7).
- Source for Argentine holidays (python `holidays` package, AR) — verify it covers 2026–2027.

Rules: English for docs, Spanish only for UI copy; no code changes; keep files tidy markdown.
```

---

## Prompt 2 — Day 1: identity, tenant scoping and the web shell

Run this after Prompt 1 is merged.

```text
You are working in the followup-agent-24x7 monorepo. Read README.md, ARCHITECTURE.md,
docs/roadmap-mvp.md (Day 1) and docs/screens-spec.md (S1, S5 shell, S8 access) before planning.
Follow the existing conventions exactly: bounded contexts in packages/core with
domain/application/infrastructure, domain imports nothing outward, the product API is the
composition root (container.py), stable error codes like {"code": "..."} mapped to Spanish in
the frontends, generated OpenAPI client in @followup/api-client-inmo24x7, shared UI in
@followup/ui. Code and docs in English; UI copy in Spanish (Argentina, voseo).

GOAL (Day 1 "Done when")
I can sign up with Google or a magic link, land on my own empty panel with the real sidebar,
and the backoffice only works for an admin user. Every tenant endpoint is scoped to the caller.

SCOPE
1. Identity context in packages/core/src/followup_core/identity:
   - Domain: Profile (id = Supabase user id, email, display name, tenant_id, role in
     owner|manager|agent|viewer, is_platform_admin), errors, repository contract.
   - A TokenVerifier port; infrastructure adapter that verifies Supabase JWTs (HS256 with
     SUPABASE_JWT_SECRET, or JWKS if configured) and a fake verifier for tests.
   - FastAPI dependencies: current_profile, require_role(...), require_platform_admin.
2. Tenancy additions: plan (trial with trial_ends_at, default 14 days) and status
   (active|suspended) on tenants; a SignUp use case that, in one transaction, creates
   tenant + owner profile + trial plan. Idempotent per user: a second call returns the
   existing tenant. Migrations in packages/core/migrations (next revision after 0001).
3. Endpoints:
   - POST /me/sign-up  {business_name}  → tenant + profile (auth required, no tenant yet).
   - GET  /me → profile + tenant summary (404 code "profile_not_found" if not signed up).
   - Existing /tenants list/create become admin-only (403 code "admin_required").
   - Add a tenant-scoped example: GET /tenant → the caller's tenant. All future tenant
     endpoints must take tenant_id from the profile, never from the request.
   Regenerate packages/api-client-inmo24x7/src/schema.ts.
4. Web (apps/inmo24x7/web):
   - Add routing (TanStack Router or React Router, pick one and justify it in the plan) and a
     Supabase auth client. Routes: /ingreso (S1), /onboarding (placeholder for Day 2 that
     only asks the business name and calls /me/sign-up), / (Inicio), /consultas,
     /propiedades, /agente, /configuracion (empty states with Spanish copy).
   - Auth guard: no session → /ingreso; session but no profile → /onboarding.
   - S1 Ingreso screen as specified: Google button, magic-link email form with sent state and
     errors, terms/privacy links (href "#" for now).
   - Sidebar labels exactly: Inicio, Consultas, Propiedades, Agente, Configuración; tenant
     name in the sidebar; sign-out.
   - API client sends the Supabase access token as a Bearer header.
5. Backoffice: same Supabase sign-in; if /me says not platform admin, show "Solo
   administradores de la plataforma." and nothing else. Keep the tenants table working.
6. Config and docs: add SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET (API) and
   VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY (panels) to .env.example, README table, config.py
   (required in production) and the CI image build args. A script or documented SQL to mark
   a user as platform admin. Remove the "no authentication" warnings that no longer apply.
   Update the README architecture diagram (Identity and Supabase Auth no longer planned).

TESTS (required, CI must stay green)
- Core unit tests with in-memory repos: SignUp creates all three, is idempotent, rejects empty
  business name; role checks.
- API integration tests with the fake verifier: 401 without token, 403 for non-admin on
  /tenants, scoping (user A can never read tenant B), /me before and after sign-up.
- Frontend: guard redirects and the Ingreso form states (vitest + testing-library, like the
  existing tenants-table test).
- ruff, pyright, eslint, typecheck, schema drift check all pass.

OUT OF SCOPE TODAY
The full onboarding wizard, agent config, invitations of other users, real Supabase project
setup (I do that by hand; use env vars and the fake verifier locally).

PROCESS
First reply with a plan only: files to add/change, the migration, the endpoint list with error
codes, the router choice, and any open question. Wait for my OK. Then implement in small
commits, run the full test and lint suite, and finish with: what changed, how I test the
"Done when" by hand, and anything you deferred.
```
