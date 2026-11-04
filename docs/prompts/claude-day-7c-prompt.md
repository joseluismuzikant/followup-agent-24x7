# Claude Code prompt — Day 7C: error monitoring, logs and LLM cost per business

Create the branch yourself first (`git checkout -b feature/day-7c`), open Claude Code at the
repo root, and paste everything inside the block. Claude will not commit anything.

Before running it (or right after, before deploying), create these accounts. Everything has
a free tier; check the current limits:

- **Sentry** (sentry.io, pick the region you prefer): one organization, projects for the
  backend (API + worker), the panel and the backoffice. Note each project's DSN, and create
  an auth token for source-map uploads and a read-only API token for the backoffice.
- **Grafana**: nothing to create. It runs self-hosted in Docker on your VM (Grafana, Loki and
  Alloy). You only add a DNS record `grafana.<domain>` pointing to the VM.

```text
You are working in the followup-agent-24x7 monorepo. Days 1–7 are merged and inmo24x7 is
ready to deploy. This session adds error monitoring, log search and a per-business LLM cost
screen to the backoffice. It moves "error monitoring and alerts" forward from Day 12.

GIT RULES — READ FIRST, THESE OVERRIDE ANY HABIT OR DEFAULT
- Do NOT run git commit, git push, git merge, git rebase, git stash, git reset, or
  git checkout/switch of branches, and do not create tags, branches or pull requests.
- Do not use `gh` to change anything on GitHub.
- Do not connect to my server, Sentry, Grafana or any production system.
- You MAY run read-only git commands (git status, git diff, git log).
- Leave every change uncommitted. End with a suggested commit split; do not run it.

READ BEFORE PLANNING
README.md, ARCHITECTURE.md, docs/roadmap-mvp.md, docs/go-live.md, deploy/ (compose.prod.yml,
Caddyfile, rehearsal), .github/workflows/ci.yml, apps/inmo24x7/api/src/inmo24x7_api/
{main,config,container,worker,http_errors,logging,middleware,tracing}.py,
packages/core/src/followup_core/conversation (domain/llm.py TokenUsage,
infrastructure/langchain_llm.py, infrastructure/langgraph_runtime.py, application/threads.py),
the backoffice (router, pages, Salud del sistema, S9) and both panels' main.tsx and api
clients.

CONVENTIONS (unchanged)
Bounded contexts with domain/application/infrastructure, container.py as composition root,
stable error codes mapped to Spanish, generated OpenAPI client, @followup/ui, Alembic
migrations only (single-head rule), the RLS/privileges rule from 7B for every new table.
Code and docs in English; UI copy in Spanish. Never send or log message text, phone numbers,
emails, tokens or names to any third party.

=====================================================================
1. SENTRY — errors from the API, the worker and both frontends
=====================================================================
- Backend (API and worker): sentry-sdk with the FastAPI and SQLAlchemy integrations, DSN from
  SENTRY_DSN (empty = off; off in tests and CI), environment = APP_ENV, release = GIT_COMMIT.
  - send_default_pii off; a before_send / before_breadcrumb hook that removes request bodies,
    query strings, headers except a safe list, cookies, and runs the same PII anonymizer the
    LangSmith client uses over every string; unit-test it with emails, Argentine phones,
    DNIs and a bearer token.
  - Tags on every event: request_id (from RequestContextMiddleware), tenant_id when known,
    job kind and job id in the worker, channel. Never the profile email.
  - Capture: unhandled exceptions (API and worker), jobs that go dead, webhook processing
    failures, Meta auth errors that put a connection in error, LLM failures after retries.
    Expected outcomes (validation errors, 4xx ApiErrors, outside_service_window) are not
    errors: do not send them.
  - Performance tracing off by default; SENTRY_TRACES_SAMPLE_RATE setting, default 0.
- Frontends (panel and backoffice): @sentry/react with DSN from VITE_SENTRY_DSN (build-time),
  release = the commit, environment from the build.
  - An error boundary around the app with a Spanish fallback ("Algo salió mal. Ya nos llegó
    el aviso.") and a "Recargar" button; unhandled rejections captured; API 5xx responses
    captured with the request id and path (never bodies).
  - No session replay. beforeSend strips URLs' query strings and runs a PII scrubber.
  - Tags: tenant_id (panel), area panel|backoffice. The user is identified by profile id only.
  - Source maps: generated in the Vite builds, uploaded to Sentry in CI with the release and
    then deleted from the image, so the served bundle has no source maps. Skipped when
    SENTRY_AUTH_TOKEN is not set.
- CSP: allow the Sentry ingest host in connect-src in deploy/Caddyfile, from a variable.
- Show the request id to users: when the panel shows an API error, add "Código de referencia:
  {first 8 chars}" so a customer can report it and you can find it.
- Alerts are configured in Sentry (document: email on new issue and on regression).

=====================================================================
2. LOGS — self-hosted Grafana + Loki + Alloy in Docker, on the same VM
=====================================================================
- deploy/compose.prod.yml: three services behind a compose profile `observability` (on by
  default in the runbook, so it can be turned off on a small VM): `loki`, `grafana` and
  `alloy`, with pinned image versions that publish arm64 and amd64 (check the current
  releases), restart policies, healthchecks and memory limits sized for the VM.
  - Alloy reads the Docker JSON logs of api, worker, web, backoffice and caddy (Docker socket
    mounted read-only), adds labels service and environment, parses level, and pushes to
    Loki on the internal network. Low-cardinality labels only (service, environment, level);
    request_id, tenant_id and job ids stay as JSON fields, queried with the json parser.
  - Loki: single-binary mode, filesystem storage on a named volume, retention
    LOKI_RETENTION_DAYS (default 14) enforced by the compactor, ingestion limits, and a
    documented disk estimate. No port published; reachable only on the internal network.
  - Grafana: Loki provisioned as the default datasource from files in deploy/grafana/
    (datasource, dashboards, alert rules), so nothing needs backing up: dashboards live in
    git. Admin password from GRAFANA_ADMIN_PASSWORD; anonymous access off; sign-up off;
    allow_embedding off; SMTP from the same settings as the app, for alerts.
  - Caddy publishes it at grafana.<domain> with HTTPS, plus an IP allowlist from
    GRAFANA_ALLOWED_IPS when set (document using an SSH tunnel instead when it is empty and
    the host is not published).
- Provisioned dashboard "inmo24x7 — operación": errors per service over time, 5xx rate,
  webhook rejections, dead jobs, LLM failures, and a log panel filtered by a request_id or
  tenant_id variable. Provisioned alert rules (email to SUPPORT_EMAIL): API or worker errors
  above a threshold in 5 minutes, any dead job, signature rejections spike, no webhook
  received for 6 hours while a connection is active.
- Make sure every API and worker log line is JSON with request_id, tenant_id when known,
  level and logger; add tenant_id where it is missing. Caddy access logs in JSON without
  query strings. The panels' API 5xx and frontend errors also reach Sentry (section 1).
- Locally: the same three services in docker-compose.yml under the `observability` profile,
  so `docker compose --profile observability up` shows the dev logs in Grafana at
  http://localhost:3000; scripts/dev.py gets an `--observability` flag. Include them in the
  rehearsal too.
- Document in deploy/: enabling, the retention and disk math, updating the images, and three
  saved LogQL queries: errors in the last hour, everything for one request id, everything for
  one tenant.

=====================================================================
3. BACKOFFICE — "Errores" and links
=====================================================================
- API: /admin/errors reads open, unresolved issues from the Sentry API (server-side
  SENTRY_API_TOKEN, SENTRY_ORG, project slugs) with title, culprit, first and last seen,
  event count, users affected, project (api/worker, panel, backoffice) and permalink;
  optional tenant_id filter using the tenant_id tag; cached for 60 seconds; if Sentry is not
  configured or fails, return {"configured": false} or {"available": false} — never a 500.
- Backoffice:
  - Salud del sistema gets an "Errores recientes" card (top 10, with counts and last seen)
    and "Ver todos en Sentry".
  - A new "Errores" page: the list with filters by project and period, each row linking to
    Sentry.
  - S9 Detalle del negocio: "Errores de este negocio (7 días)" with the count and the latest
    five, plus "Ver logs" opening Grafana Explore with a prefilled LogQL query for that
    tenant (GRAFANA_URL and LOKI_DATASOURCE settings; hidden when not set).
  - A "Buscar por código de referencia" box on Errores: opens Grafana Explore for that
    request id (and Sentry's search for the request_id tag).

=====================================================================
4. LLM USAGE AND COST PER BUSINESS
=====================================================================
- Record every LLM call, not just per turn: a core table llm_usage (id, tenant_id,
  thread_id, channel, is_test, operation extract|compose_reply, provider, model,
  input_tokens, output_tokens, cached_input_tokens when the provider reports it, latency_ms,
  succeeded, cost_usd NUMERIC, price_version, created_at), indexed for month/tenant queries.
  - Written in its own short transaction (a separate session), so usage is kept even when
    the turn later rolls back: the provider still charges for those tokens. Failures to write
    usage are logged and never break a turn.
  - Capture the usage metadata LangChain returns for every supported provider (check what
    each of the five providers reports, including cached tokens); when a provider returns
    no usage, store zeros and mark it so the screen can say "sin datos".
- Prices: a versioned file in the repo (e.g. apps/inmo24x7/api/src/inmo24x7_api/billing/
  llm_prices.toml) with, per provider:model, USD per 1M input tokens, per 1M output tokens,
  per 1M cached input tokens, effective_from date and a source URL. DO NOT INVENT PRICES:
  create the file with the structure, one commented example, and empty entries for the
  models configured in .env.example; I fill in the numbers. cost_usd is computed at write
  time with the price in force at created_at; a model without a price stores NULL cost.
  A startup warning (not an error) when LLM_MODEL has no price. A script
  scripts/recompute_llm_costs.py --from DATE recomputes costs after I fix a price, dry-run
  by default.
- Meta charges too: count, per business and month, the template messages sent (billable by
  Meta) and show the count next to the LLM cost, without a price.
- Backoffice "Consumo" page:
  - Month selector (default: current month, tenant timezone not needed: use UTC months and
    say so in the page).
  - Totals: LLM cost in USD, input and output tokens, conversations (threads with an inbound
    message that month), cost per conversation, and the share that came from simulator
    tests.
  - A table per business, sorted by cost: plan, conversations, LLM calls, tokens in/out, cost,
    cost per conversation, simulator share, template messages, and a flag when a model had no
    price.
  - Click a business: a daily chart of cost (bars) and conversations (line) for the month,
    and the split by operation (extract vs compose_reply) and by model.
  - "Exportar CSV" with the table.
  - S9 gets a "Consumo este mes" card (cost, conversations, cost per conversation, link to the
    Consumo page filtered by that business).
- Cost alert: LLM_MONTHLY_COST_ALERT_USD (empty = off). A daily job emails SUPPORT_EMAIL when
  a business passes it for the month (once per business and month) and records an audit
  event. Keep the simulator daily limit as it is.

TESTS (all must pass; Sentry and Grafana are never called for real)
- Sentry scrubbers (backend and frontend): no PII, no bodies, no query strings; expected
  errors are not sent; tags present; disabled when the DSN is empty.
- /admin/errors: admin only, Sentry API mocked at the HTTP level, cache, unconfigured and
  failing Sentry return the flags, tenant filter.
- Usage: a row per LLM call with the right tokens and cost; kept when the turn rolls back;
  NULL cost without a price; price changes by effective_from; the recompute script dry-run
  and apply; providers without usage.
- Consumo API: totals, per-business table, simulator share, cost per conversation,
  month boundaries, CSV export, template counts; the cost alert fires once per month.
- Migrations: single head, the new tables pass the RLS test.
- Frontend: error boundary fallback, "Código de referencia" on API errors, Errores page
  states (configured, unconfigured, unavailable), S9 cards, Consumo page with chart and
  table, CSV.
- Run everything CI runs: uv run ruff check ., uv run ruff format --check ., uv run pyright,
  uv run alembic upgrade head, uv run --all-packages pytest, schema regeneration + git diff
  check, pnpm lint, pnpm typecheck, pnpm test. Fix failures; do not skip or xfail tests.

CONFIG AND DOCS
- New settings (runtime unless noted): SENTRY_DSN, SENTRY_TRACES_SAMPLE_RATE, SENTRY_API_TOKEN,
  SENTRY_ORG, SENTRY_PROJECTS, VITE_SENTRY_DSN (build-time, per panel), SENTRY_AUTH_TOKEN (CI
  secret, source maps only), GRAFANA_URL (for the backoffice links), LOKI_DATASOURCE,
  GRAFANA_ADMIN_PASSWORD, GRAFANA_ALLOWED_IPS, LOKI_RETENTION_DAYS,
  LLM_MONTHLY_COST_ALERT_USD. None is required in production; each feature
  turns off cleanly without its settings. Add them to .env.example, deploy/.env.production.example,
  the README env table and the CI build args/secrets.
- docs/go-live.md: a section "Monitoring" with the Sentry setup steps and alert rules, the
  grafana.<domain> DNS record, first Grafana login and password change, checking the
  provisioned dashboard and alerts, and a reminder that Sentry receives operational data
  (no message text) and should be in the privacy policy; Loki and Grafana stay on our VM.
- ARCHITECTURE.md: what goes to Sentry, Loki and LangSmith and what never does; usage and
  cost recording; price versioning.
- docs/roadmap-mvp.md: add Day 7C (done or what moved) and remove error monitoring from Day 12
  (keep "alerts on failed reminders" there, which needs Cuentas Claras).

OUT OF SCOPE
Charging customers for usage, ARS conversion, Meta's prices per template, self-hosted
Sentry, Grafana Cloud, embedding Grafana inside the backoffice (links only), metrics and
traces backends (Prometheus, Tempo), session replay.

PROCESS
1. Plan first (use plan mode): Sentry setup per app and the scrubbing, which errors are
   captured, the Alloy/Loki config, the /admin/errors contract, the llm_usage table and how it
   is written outside the turn transaction, the price file format, the Consumo queries and
   screens, the memory and disk budget of the observability services on the VM, config,
   open questions. Wait for my OK.
2. Implement: usage and cost first (it needs no external account), then the self-hosted
   Grafana/Loki/Alloy stack (try it locally with the compose profile), then Sentry backend,
   Sentry frontends and CI source maps, then the backoffice pages.
3. Finish with what changed, what I must create in Sentry and where each value goes, how to test locally (including a forced test error), what you deferred, and the
   suggested commit split. Do not commit.
```
