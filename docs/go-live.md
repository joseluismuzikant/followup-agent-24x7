# inmo24x7 go-live runbook

Follow it in order. Replace `<domain>` with your domain (for example `inmo24x7.com.ar`) and
`<ref>` with your Supabase project ref. Before the first real deploy, run the local
production rehearsal once (`deploy/rehearsal.md`): it exercises the same compose file,
`deploy.sh`, migrations, Caddy, backup and restore.

Time needed: about 2 hours of your own work, plus waiting for DNS and Meta's reviews.

## 0. What must already exist

| What | Where |
| --- | --- |
| A domain whose DNS you control | your registrar |
| An Oracle Cloud ARM VM in São Paulo (or any Linux VM with a public IPv4) | Oracle Cloud |
| An Object Storage bucket and a Customer Secret Key (S3-compatible access) | Oracle Cloud |
| A Supabase project in São Paulo (`sa-east-1`) | Supabase |
| A Google OAuth client (Web application) | Google Cloud Console |
| A transactional email provider with SMTP (Resend, Brevo, Amazon SES, ...) | the provider |
| Meta: business verification, Tech Provider, an app with WhatsApp and Facebook Login for Business | Meta Business / App Dashboard |
| An LLM API key with balance | your model provider |
| An age key pair for backups: `age-keygen -o ~/inmo24x7-backup.agekey` | your machine |

## 1. DNS

Three `A` records to the VM's public IPv4 (TTL 300 while setting up):

| Name | Type | Value |
| --- | --- | --- |
| `api.<domain>` | A | `<vm-ip>` |
| `app.<domain>` | A | `<vm-ip>` |
| `admin.<domain>` | A | `<vm-ip>` |
| `grafana.<domain>` | A | `<vm-ip>` (only if you publish Grafana; section 12b) |

Check: `dig +short app.<domain>` prints the IP. Caddy gets the certificates on the first
request once DNS resolves and ports 80/443 are open.

## 2. The VM

Follow `deploy/bootstrap.md`: open 80/443 in the VCN security list, then run
`deploy/bootstrap.sh` once. From then on, connect as `ssh deploy@<vm-ip>`; everything lives
in `/opt/inmo24x7`.

## 3. Supabase

**Database**

1. **Settings → Data API: turn off "Enable Data API".** Required: the anon key is public in
   the panel bundle, and we never use the Data API. (The `0011` migration also enables row
   level security on every table and revokes `anon` / `authenticated`, as a second lock.)
2. **Connect → Session pooler** (port **5432**): copy the URI. This is `DATABASE_URL`, with
   `postgresql+psycopg://` instead of `postgresql://` and `?sslmode=require` at the end:
   `postgresql+psycopg://postgres.<ref>:<password>@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require`.
   - Never the **transaction** pooler (port 6543): it has no prepared statements, which
     psycopg and the LangGraph checkpointer need. The API refuses to start with it.
   - The **direct connection** (`db.<ref>.supabase.co:5432`) only works over IPv6 unless you
     buy the IPv4 add-on; use it only if the VM has IPv6.
3. **Connection math:** the session pooler gives every client connection its own server
   connection. The defaults use API 5 + 1 overflow, worker 5, one more each for LLM usage
   rows (written outside the turn), and up to 2 one-offs (migration, backup): 15, the
   smallest compute's pool (Database → Settings → Connection pooling shows yours). Raise `API_DB_POOL_SIZE` / `WORKER_DB_POOL_SIZE` only
   with a bigger plan.

**Auth**

4. **Authentication → URL Configuration:**
   - Site URL: `https://app.<domain>`
   - Redirect URLs: `https://app.<domain>/**` and `https://admin.<domain>/**`
5. **Authentication → Sign In / Providers → Email:** enabled, **"Confirm email" ON**. The
   panel only offers Google and the magic link; Supabase has no separate switch that turns
   off email+password sign-ups but keeps magic-link sign-ups ("Allow new users to sign up"
   turns off both). With "Confirm email" on, anyone signing up through the API with a
   password must still prove the email, and the API only lets a confirmed email join a
   business an admin created for it.
6. **Google:**
   - In Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID → Web
     application. Authorized JavaScript origins: `https://app.<domain>`. Authorized redirect
     URI: the callback Supabase shows on its Google provider page
     (`https://<ref>.supabase.co/auth/v1/callback`).
   - OAuth consent screen: app name inmo24x7, your support email, publish it to production.
   - Back in Supabase → Providers → Google: enable it, paste the client id and secret.
7. **Authentication → Emails → SMTP settings:** your provider's host, port 587, user,
   password, sender `inmo24x7 <acceso@<domain>>`. The built-in sender is rate-limited and
   not for production. Verify the sending domain (SPF, DKIM) at the provider.
8. **Authentication → Emails → Templates → Magic link**, subject `Tu link para entrar a
   inmo24x7`, body:

   ```html
   <h2>Entrá a inmo24x7</h2>
   <p>Tocá el botón para entrar a tu panel. El link vale por una hora y sirve una sola vez.</p>
   <p><a href="{{ .ConfirmationURL }}">Entrar a inmo24x7</a></p>
   <p>Si no pediste este link, ignorá este email.</p>
   ```

   Use the same tone for "Confirm signup" (subject `Confirmá tu email`, button `Confirmar mi
   email`).
9. **Authentication → JWT Keys:** use the asymmetric signing keys (migrate if the project
   still uses the legacy secret). The API verifies tokens with
   `SUPABASE_JWKS_URL=https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` and checks the
   issuer `https://<ref>.supabase.co/auth/v1`.
10. **Settings → API Keys:** copy the anon (or publishable) key. It is public: it goes in
    the panel builds and in `SUPABASE_ANON_KEY`. Never use the service role / secret key
    anywhere in this app.

## 4. GitHub (image builds)

Repository → Settings → Secrets and variables → Actions → **Variables**:

| Variable | Value |
| --- | --- |
| `INMO24X7_API_URL` | `https://api.<domain>` |
| `INMO24X7_PANEL_URL` | `https://app.<domain>` |
| `SUPABASE_URL` | `https://<ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | the anon / publishable key (public; a secret of that name also works) |
| `META_APP_ID` | the Meta app id |
| `META_EMBEDDED_SIGNUP_CONFIG_ID` | the Embedded Signup configuration id (step 8) |

Optional, for Sentry in the panels (section 12a): variables `SENTRY_ORG`, `SENTRY_DSN_PANEL`,
`SENTRY_DSN_BACKOFFICE`, `SENTRY_PROJECT_PANEL`, `SENTRY_PROJECT_BACKOFFICE`, and the
**secret** `SENTRY_AUTH_TOKEN` (source maps). Without them the panels build without Sentry.

The `images` job fails on `master` until all six required variables are set. Then push (or re-run CI on)
`master`: it builds `ghcr.io/<owner>/<repo>/inmo24x7-{api,web,backoffice}:sha-<commit>` for
amd64 and arm64. Note the full commit sha: that is what you deploy.

## 5. Pulling the images on the VM

Either make the three packages public (GitHub → your profile → Packages → each one →
Package settings → Change visibility), or log the VM in with a token that only reads
packages:

```bash
echo <token-with-read:packages> | docker login ghcr.io -u <github-user> --password-stdin
```

## 6. `.env.production` on the VM

```bash
cd /opt/inmo24x7
cp .env.production.example .env.production
chmod 600 .env.production
nano .env.production
```

Every variable has a comment. Where each value comes from:

- `IMAGE_PREFIX`: `ghcr.io/<owner>/<repo>` in lowercase.
- The domains and `ACME_EMAIL`.
- `DATABASE_URL`: step 3.2.
- `SUPABASE_*`: steps 3.9 and 3.10.
- `LLM_MODEL` and its key.
- `META_APP_ID`, `META_APP_SECRET`, `META_EMBEDDED_SIGNUP_CONFIG_ID`: step 8.
- `WHATSAPP_VERIFY_TOKEN`: `openssl rand -hex 24`.
- `TOKEN_ENCRYPTION_KEY`: `python3 -c "import base64, os;
  print(base64.b64encode(os.urandom(32)).decode())"`. **Keep a copy in your password
  manager**: without it no stored WhatsApp token can be read.
- `SMTP_*`, `EMAIL_FROM`, `SUPPORT_EMAIL`.
- `BACKUP_AGE_RECIPIENT`: the `age1...` public key.
- `BACKUP_REMOTE` and `RCLONE_S3_*`: Oracle → Storage → Buckets (namespace, bucket) and
  User settings → Customer secret keys.

Never set `REHEARSAL` here.

## 7. First deploy

```bash
cd /opt/inmo24x7
docker compose --project-name inmo24x7 --env-file .env.production -f compose.prod.yml build backup
./deploy.sh <full-commit-sha>
```

`deploy.sh` pulls the images, runs `alembic upgrade head` once (it stops there if the
migration fails, and nothing restarts), starts the five services, and waits for
`/health/ready` to report that commit. If the new version never gets ready it puts the
previous one back, and says that migrations were **not** rolled back. Later deploys are the
same command with a newer sha (or the Deploy workflow, step 12).

Check from your machine:

```bash
curl -s https://api.<domain>/health/ready     # {"status":"ready", ..., "commit":"<sha>"}
curl -sI https://app.<domain> | grep -i strict-transport-security
```

## 8. Meta

In the [App Dashboard](https://developers.facebook.com/apps):

1. **WhatsApp → Configuration → Webhook:** callback URL `https://api.<domain>/webhooks/whatsapp`,
   verify token = `WHATSAPP_VERIFY_TOKEN`. Then subscribe the fields **messages** and
   **account_update**.
2. **App settings → Basic:** app id (`META_APP_ID`), app secret (`META_APP_SECRET`); App
   domains `app.<domain>`; privacy policy and terms URLs (required for Live mode).
3. **Facebook Login for Business → Settings:** allowed domains for the JavaScript SDK
   `https://app.<domain>`; valid OAuth redirect URIs `https://app.<domain>/`.
4. **Facebook Login for Business → Configurations → Create:** login variation *WhatsApp
   Embedded Signup*, permissions `whatsapp_business_management` and
   `whatsapp_business_messaging`. Its id is `META_EMBEDDED_SIGNUP_CONFIG_ID` (GitHub variable
   and `.env.production`; rebuild the images if you change it).
5. **Tech Provider** onboarding complete, business verification approved, and the app in
   **Live** mode (top bar).
6. **WhatsApp Manager → Message templates:** `confirmacion_visita` (README, "Testing the
   inbox") approved; enter it per business in the backoffice.

After changing `.env.production`, restart: `./deploy.sh <same sha>` (idempotent).

## 9. The first platform admin

Sign in at `https://admin.<domain>` (or the panel) with your email and finish the sign-up so
your profile exists. Then:

```bash
cd /opt/inmo24x7
docker compose --project-name inmo24x7 --env-file .env.production -f compose.prod.yml \
  run --rm api python scripts/make_admin.py <your-email>
```

Reload the backoffice: Negocios, Salud del sistema and Planes appear. Then check that an
owner claim works once: Backoffice → Dar de alta un negocio with a second email you own,
sign in with it (magic link), and it lands in that business.

## 10. Backups

```bash
cd /opt/inmo24x7
./backup-now.sh                                # the first one, now; ends with status=ok
sudo systemctl enable --now inmo24x7-backup.timer
systemctl list-timers inmo24x7-backup.timer    # next run 06:00 UTC
```

Then run the **restore drill** in `deploy/restore.md` (copy the identity file to the VM for
it, `./restore.sh latest ~/inmo24x7-backup.agekey`, then `shred -u` it).

## 11. Done when: from sign-up to a working agent on WhatsApp in under 10 minutes

With a stopwatch, a brand-new account (a new email, a WhatsApp number that is not on the
Cloud API, and a second phone):

| Step | Target |
| --- | --- |
| `https://app.<domain>` → Continuar con Google (or the magic link) → business name → Crear | 1 min |
| Tu agente: name, tone, hours, questions → Guardar | 2 min |
| Probalo: 3–4 messages in the simulator | 1 min |
| Conectá WhatsApp: Meta's popup, choose or add the number, SMS code | 3–4 min |
| From the second phone, write to the number: the agent answers on WhatsApp | 1 min |
| Inicio shows the lead; the "Mensaje de prueba" row is green | — |

Write down the total and where time went. Common delays: the number still registered in the
WhatsApp app (S4 explains it in Spanish), Meta's popup blocked by the browser, or the
business verification still pending (the agent works; "Pendiente en Meta" shows the links).
When it passes, mark Day 7 done in `docs/roadmap-mvp.md`.

## 12. Optional: deploy from GitHub

Repository → Settings → Environments → **production**: secrets `DEPLOY_HOST` (the VM IP),
`DEPLOY_USER` (`deploy`), `DEPLOY_SSH_KEY` (a private key whose public half is in
`/home/deploy/.ssh/authorized_keys`), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan <vm-ip>`); and the
repository variable `DEPLOY_ENABLED=true`. Then Actions → Deploy → Run workflow with the full
sha. It runs the same `deploy.sh` over SSH.

## 12a. Monitoring: Sentry (errors)

Optional but recommended before the first customer. The free Developer plan is enough to start.

1. **Create three projects** in one organization: `inmo24x7-api` (platform Python/FastAPI;
   the API and the worker share it), `inmo24x7-panel` and `inmo24x7-backoffice` (React).
   Note the organization slug (`SENTRY_ORG`) and, if it lives in the EU region, use
   `SENTRY_API_URL=https://de.sentry.io`.
2. **Project settings → Security & Privacy:** "Data Scrubber" and "Use Default Scrubbers" ON,
   "Prevent Storing of IP Addresses" ON. Our own scrubbing runs first; this is the second lock.
3. **DSNs** (Project → Client Keys): the API's goes in `.env.production` as `SENTRY_DSN`; the
   panels' go to GitHub variables `SENTRY_DSN_PANEL` and `SENTRY_DSN_BACKOFFICE` (build time).
   The ingest host of those DSNs (`https://o<id>.ingest.us.sentry.io`) goes in
   `.env.production` as `SENTRY_INGEST_HOST`, so the CSP lets the panels reach it.
4. **Source maps:** Settings → Auth Tokens → an *organization* token with `project:releases`
   and `org:read`, saved as the GitHub **secret** `SENTRY_AUTH_TOKEN`, plus the variables
   `SENTRY_PROJECT_PANEL=inmo24x7-panel` and `SENTRY_PROJECT_BACKOFFICE=inmo24x7-backoffice`.
   CI uploads the maps for the release (the commit) and deletes them from the image.
5. **The backoffice's Errores page:** Settings → Custom Integrations → *Create New
   Integration* → Internal, permissions **Issue & Event: Read** (nothing else). Its token is
   `SENTRY_API_TOKEN`; `SENTRY_PROJECTS=api=inmo24x7-api,panel=inmo24x7-panel,backoffice=inmo24x7-backoffice`.
6. **Alerts** (each project → Alerts → Create alert → Issues): "A new issue is created" →
   email to the team; and "The issue changes state from resolved to unresolved"
   (regression) → email. Keep the default "Notify on every new issue" off for noisy projects.
7. **Check end to end:** redeploy, then Backoffice → Errores → **Enviar errores de prueba**.
   Within a minute Sentry shows `SentryTestError` (api) with the request id as a tag, and
   "Error de prueba del panel" (backoffice). Resolve both.
8. **Privacy policy:** Sentry receives operational data (stack traces, URLs without query
   strings, browser and OS, profile and business ids), never message text, names, phones or
   emails. Name it in the privacy policy as a processor (and its region). Loki and Grafana stay
   on our VM.

## 12b. Monitoring: logs (Loki + Alloy + Grafana on the VM)

On by default (`COMPOSE_PROFILES=observability`); about 1 GB of RAM and 1 GB of disk at MVP
traffic. Details, disk math and LogQL in `deploy/observability.md`.

1. In `.env.production`: `GRAFANA_ADMIN_PASSWORD` (long, random), `ALERTS_EMAIL_FROM` (a plain
   address of your SMTP domain), `LOKI_RETENTION_DAYS=14`, and either
   `GRAFANA_DOMAIN=grafana.<domain>` (plus its DNS record, and optionally
   `GRAFANA_ALLOWED_IPS` with your office/home IPs) or empty to use an SSH tunnel
   (`ssh -L 3000:127.0.0.1:3000 deploy@<vm-ip>` → http://localhost:3000).
2. `GRAFANA_URL=https://grafana.<domain>` (or empty to hide the backoffice's links) and
   `LOKI_DATASOURCE=loki`.
3. Deploy (`./deploy.sh <sha>` starts loki, alloy and grafana too).
4. **First login** at Grafana as `admin` with `GRAFANA_ADMIN_PASSWORD`, then change it
   (Profile → Change password) and keep it in the password manager.
5. **Check:** Dashboards → inmo24x7 → *inmo24x7 — operación* shows API requests and the
   panels; Explore → `{service="api"}` has lines from the last minutes. Alerting → Alert rules
   lists four rules (errors, dead jobs, signature rejections, no webhooks for 6 h), all
   *Normal*; Contact points → *soporte* → **Test** delivers an email to `SUPPORT_EMAIL`.
6. Optional: `LLM_MONTHLY_COST_ALERT_USD` (for example `20`) emails `SUPPORT_EMAIL` when a
   business's LLM cost passes it in a month (Backoffice → Consumo shows the numbers). Fill in
   the real prices in `billing/llm_prices.toml` first, or costs stay empty.

## After go-live

- Health: Backoffice → Salud del sistema (jobs, webhooks, failed sends by Meta code, recent
  errors). Errors: Backoffice → Errores, or Sentry. Costs: Backoffice → Consumo.
- A customer reports "Código de referencia: 1a2b3c4d": Backoffice → Errores → Buscar por código
  de referencia (logs in Grafana, errors in Sentry).
- Logs: Grafana, or `docker compose --project-name inmo24x7 --env-file .env.production -f compose.prod.yml logs -f api worker`.
- Rollback to the previous version: `./deploy.sh <previous sha>` (`state/previous_tag`).
  Migrations stay applied, which is why they must be backward compatible.

---

## 3-minute demo script

Record at 1080p, panel in Spanish, one real number connected and a second phone at hand.

1. **0:00 – The problem (15 s).** Inicio of a business with data: "una consulta a las 23:10,
   respondida en 5 segundos".
2. **0:15 – Sign-up (25 s).** A new window: Continuar con Google → "Inmobiliaria Demo" →
   the wizard opens.
3. **0:40 – The agent (25 s).** Tu agente: name "Sofía", tone, hours; the questions list.
   Guardar.
4. **1:05 – Probalo (30 s).** "Hola, busco alquilar en Palermo" → the agent asks, shows
   three property cards with links, offers visit times; "Lo que el agente ya sabe" fills in.
5. **1:35 – Conectar WhatsApp (25 s).** Meta's popup (cut the wait): the status card turns
   green; "Pendiente en Meta" links.
6. **2:00 – On a real phone (30 s).** Write to the number: the answer arrives in seconds;
   tap a visit time button.
7. **2:30 – Consultas (20 s).** The lead under "Para atender" with the visit; Tomar la
   conversación, reply as the team, Confirmar visita.
8. **2:50 – Close (10 s).** Inicio: KPIs for the week. "inmo24x7: nunca más una consulta
   sin responder".
