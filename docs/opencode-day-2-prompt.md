# OpenCode prompt — Day 2: onboarding wizard and agent configuration

Paste everything inside the block into a new OpenCode session at the repo root, on a new
branch (for example `feature/day-2`).

```text
You are working in the followup-agent-24x7 monorepo on Day 2 of docs/roadmap-mvp.md.
Before planning, read README.md, ARCHITECTURE.md, docs/roadmap-mvp.md (Day 2) and
docs/screens-spec.md (S2, S5, "inmo24x7 — Agente", "inmo24x7 — Configuración", and S9's
onboarding checklist). Then read the Day 1 code: packages/core/src/followup_core/{identity,
tenancy}, apps/inmo24x7/api/src/inmo24x7_api/{auth,me,container,main,config}.py and
apps/inmo24x7/web/src.

Follow the existing conventions exactly: bounded contexts with domain/application/
infrastructure, the domain imports nothing outward, container.py is the composition root,
errors are stable codes like {"code": "..."} mapped to Spanish in the frontends, the
generated OpenAPI client in @followup/api-client-inmo24x7 (regenerate schema.ts), shared
components in @followup/ui. Code and docs in English; UI copy in Spanish (Argentina, voseo).
Every tenant endpoint takes tenant_id from the caller's profile, never from the request.

=====================================================================
PART 0 — Day 1 fixes (do these first, as their own commit)
=====================================================================
0.1 SECURITY: apps/inmo24x7/api/Dockerfile turns SUPABASE_JWT_SECRET, SUPABASE_ANON_KEY,
    SUPABASE_URL and SUPABASE_JWKS_URL into build ARGs and bakes them into the image as ENV,
    and .github/workflows/ci.yml passes the secrets as build-args. Anyone who can pull the
    image can read the JWT secret with `docker inspect` and forge tokens for any user,
    admins included. Remove those ARG/ENV lines from the API Dockerfile and the SUPABASE_*
    build-args for the API from CI. The API reads them only at runtime (docker run -e /
    env file). Keep VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY for the web and backoffice
    builds (the anon key is public by design). Update the README "Images" and env sections.
0.2 JWT verification (packages/core/.../identity/infrastructure/supabase_verifier.py):
    - JWKS path: accept ES256 and RS256, and reuse one cached PyJWKClient instead of
      creating one per request.
    - Validate the issuer (`{SUPABASE_URL}/auth/v1`) in addition to the audience.
    - config.py: production requires SUPABASE_URL plus EITHER SUPABASE_JWT_SECRET OR
      SUPABASE_JWKS_URL, not the secret specifically. The API does not need
      SUPABASE_ANON_KEY; stop requiring it.
    - Log a startup warning when the fake verifier is active (development only).
0.3 Redirect loop: in web RequireProfile, any /me error other than profile_not_found
    navigates to /ingreso, and RedirectIfAuthed sends a signed-in user back to "/". If the
    API is down or rejects the token, the browser loops forever. Instead: on 401, sign out
    and go to /ingreso; on any other error, show an error card with "Reintentar" and
    "Cerrar sesión" (Spanish copy). Add tests for both cases and for the
    profile_not_found → /onboarding redirect.
0.4 Self-serve sign-up must not fail because another business has the same name: SignUp
    picks the next free slug (inmobiliaria-sur, inmobiliaria-sur-2, ...). Keep the 409 for
    the admin POST /tenants. Update the core test that expects a duplicate-slug error.

=====================================================================
PART 1 — Day 2 goal
=====================================================================
Done when: a new account goes from sign-up to the "Probalo" step in under 3 minutes without
help, leaves with "Terminar después", and lands on the same step when it comes back. The
Agente and Configuración screens edit the same data the wizard saved.

DATA MODEL (core, new migration after 0002)
1. Onboarding progress, in Tenancy: per tenant, current_step (business | agent | try |
   whatsapp | done), the completed steps with timestamps, finished_at. Steps can only be
   moved forward by the use cases; going back is allowed for editing but never "uncompletes"
   a step.
2. Business settings, in Tenancy (not versioned): business_type, timezone (default
   America/Argentina/Buenos_Aires), team hours, notification emails (1–5 valid addresses).
   Team hours are a structured weekly schedule {weekday, opens, closes}[]. The UI presets
   map to it: "Lunes a viernes, 9 a 18" and "Lunes a sábado, 9 a 13". Add a pure domain
   function is_within_team_hours(settings, datetime) with tests (Day 6 KPIs use it).
3. Agent configuration, versioned: agent_config_versions(tenant_id, version, created_at,
   created_by_profile_id, config JSONB), unique (tenant_id, version). Saving creates a new
   version only if something changed; the current config is the highest version. The domain
   object is product-agnostic:
     - agent_name (1–40 chars)
     - tone: warm | professional | formal (UI: Cercano, Profesional, Formal)
     - after_hours_mode: keep_answering_and_propose_visit (the only value today; keep the field)
     - qualification_questions: ordered list of
         {key, label, kind: choice|text|number|money|boolean, options?, enabled}
       `key` is a stable slug the graph will read on Days 3–4 to fill "Lo que el agente ya
       sabe". Questions are DATA: nothing in the code may hard-code the list. Custom questions
       from "+ Agregar una pregunta" get kind text and key custom_<n>; limit 10 questions.
4. Product defaults live in apps/inmo24x7/api, not in core: agent name "Sofía", tone warm,
   and these questions in order, with these keys:
     operation ("Si busca comprar o alquilar", choice: compra/alquiler)
     zone ("Zona o barrio", text)
     budget ("Presupuesto", money)
     mortgage_approved ("Si tiene crédito hipotecario aprobado", boolean)
     rooms ("Cantidad de ambientes", number)
   Inject the defaults into the core use cases through the container.

SETUP CHECKLIST
S5 and S9 show different five-item lists. Build ONE server-side SetupChecklist computed from
facts: account_created, agent_configured, agent_tested, whatsapp_connected, own_properties,
meta_business_verified. Facts that later days own (tested on Day 3, properties on Day 4,
WhatsApp on Day 5/7, Meta on Day 7) come from small provider functions that return false
today, so those days only plug in a provider. The panel shows S5's five items (cuenta,
agente, WhatsApp, propiedades, verificar empresa en Meta) with "N de 5 listos". The full fact
set is returned for the backoffice to use on Day 7.

API (all tenant-scoped; writes need owner or manager, otherwise 403 "forbidden")
- POST /me/sign-up now takes {business_name, business_type} and also creates the onboarding
  record (current_step = agent) and the default business settings.
- GET  /onboarding → {current_step, completed_steps, finished, checklist}
- POST /onboarding/advance {to_step} → validates order (422 "onboarding_step_invalid")
- GET  /agent-setup → {config, version, updated_at, business_hours, notification_emails,
  defaults}
- PUT  /agent-setup → saves agent config and business hours/emails in ONE transaction, the
  form in step 2 and on Agente. Validation codes: agent_name_invalid, questions_invalid,
  team_hours_invalid, notification_email_invalid.
- GET/PUT /tenant/settings → business name, business type, hours, notification emails
  (Configuración). Renaming the business does not change the slug.
- GET  /agent-setup/versions → the latest 20 versions (version, created_at, author email).
Unit tests in core with in-memory repos; API integration tests against Postgres covering
scoping (tenant A can never read or write tenant B), role checks, versioning (no-op save does
not create a version) and step-order validation.

WEB (apps/inmo24x7/web)
- /onboarding becomes the wizard with a progress header "Paso N de 5" and the step names Tu
  negocio, Tu agente, Probalo, WhatsApp, Listo, plus "Terminar después" in the header. The
  route reads the saved step; /onboarding/:step deep links only to completed steps or the
  current one.
- Step 1 Tu negocio: business name + business type (Inmobiliaria, Red o franquicia, Corredor/a
  independiente, Desarrolladora). Submitting calls /me/sign-up. This replaces the Day 1
  onboarding page.
- Step 2 Tu agente, exactly per S2: subtitle "Ya está todo completo con lo que mejor funciona
  para inmobiliarias. Cambiá lo que quieras o seguí con esto."; Nombre del agente with live
  preview «Hola, soy {nombre}, de {negocio}»; Tono segmented control; qualification list with
  enable/disable, reorder (up/down buttons are fine), edit label, delete custom ones, "+
  Agregar una pregunta"; hint "De a una pregunta por mensaje, y siempre después de mostrarle
  opciones."; Horario de tu equipo presets; "Avisarme de cada lead en" email; the after-hours
  note; buttons "← Volver", "Usar lo recomendado" (resets the form to defaults, does not
  save), "Guardar y probar mi agente" (PUT /agent-setup, then advance to try).
  Build this form as ONE component reused by the Agente page.
- Step 3 Probalo: placeholder until Day 3. Card "Muy pronto vas a poder chatear con tu agente
  acá", a read-only summary of the saved config, buttons "← Ajustar el agente" and "Me gusta,
  conectar WhatsApp" (advances).
- Step 4 WhatsApp: placeholder until Day 7 with the three explained steps from S4 (static)
  and "Hacerlo más tarde y seguir probando en el simulador" (advances to done).
- Step 5 Listo: what is ready and what is pending (from the checklist), "Ir a mi panel".
- Routing rules: after login, an unfinished onboarding opens the wizard at the saved step.
  "Terminar después" goes to the panel for this session; the panel checklist has a
  "Continuar configuración" link that resumes at the saved step.
- Inicio: the S5 checklist card "Te falta poco para dejarlo completo", "N de 5 listos", done
  items with ✓ and pending ones as links. Keep the rest of Inicio empty with a short Spanish
  empty state; KPIs are Day 6.
- Agente page: the shared form plus "Versión N · actualizada {fecha}" and a collapsible
  history list. Viewers and agents see it read-only.
- Configuración page: Tu negocio (name, type), Horario del equipo, Avisos de nuevos leads
  (emails), Cuenta (owner email, plan "Prueba · N días", Cerrar sesión). Hours and emails are
  the same data as in step 2.
- Map every new error code to Spanish in lib/api-errors.ts.
- If a component is reusable by Cuentas Claras (wizard stepper, segmented control, checklist
  card, form field), put it in @followup/ui.
Frontend tests (vitest + testing-library): stepper navigation and resume, "Usar lo
recomendado" resets the form, greeting preview updates, add/disable/reorder questions,
read-only mode for viewers, checklist rendering.

DOCS
- ARCHITECTURE.md: where onboarding, business settings and agent config live and why the
  defaults are in the product.
- docs/roadmap-mvp.md: mark Day 1 done (with the Part 0 fixes) and Day 2 done or note what
  moved.

OUT OF SCOPE
The chat simulator and any LLM (Day 3), properties (Day 4), sending the lead email (Day 5),
WhatsApp connection (Day 7), inviting users.

PROCESS
1. Reply first with a plan only: Part 0 changes, migration (tables, columns, constraints),
   use cases, the endpoint list with request/response shapes and error codes, the web routes
   and components, what goes into @followup/ui, and open questions. Wait for my OK.
2. Implement in small commits (Part 0 first). Run everything CI runs: ruff check, ruff
   format --check, pyright, alembic upgrade head, pytest, schema regeneration + drift check,
   pnpm lint, typecheck, test.
3. Finish with what changed, how to test the "Done when" by hand with a stopwatch, and
   anything you deferred.
```
