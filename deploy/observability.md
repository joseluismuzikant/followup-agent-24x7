# Logs on the VM: Loki + Alloy + Grafana

Everything the containers print stays on the VM, searchable for `LOKI_RETENTION_DAYS` (14):

```text
api, worker, web, backoffice, caddy ─(Docker json-file logs)─▶ alloy ─▶ loki ◀─ grafana ─▶ email alerts
```

- **Alloy** (`observability/alloy/config.alloy`) discovers this compose project's containers
  through the Docker socket (mounted read-only) and reads their logs. It drops the API's own
  healthcheck lines, adds the labels `service`, `environment` and `level` (lowercased; plain
  nginx lines count as `info`), and pushes to Loki.
- **Loki** (`observability/loki/config.yaml`): single binary, filesystem storage on the
  `loki_data` volume, the compactor deletes what is older than the retention. No port is
  published; only Alloy and Grafana reach it, on the compose network.
- **Grafana**: Loki as the default datasource (uid `loki`), the dashboard *inmo24x7 —
  operación* and four email alert rules, all provisioned from
  `observability/grafana/` (dashboards live in git, so nothing to back up; edits in the UI
  are not kept). Anonymous access, sign-up and embedding are off.

Labels stay few on purpose: Loki indexes labels, and `request_id` or `tenant_id` as labels
would create a stream per request. They are JSON fields of each line; query them with
`| json`.

## Turning it on and off

On by default: `.env.production` has `COMPOSE_PROFILES=observability`, and `deploy.sh` then
pulls and starts `loki`, `alloy` and `grafana` with the app. It needs
`GRAFANA_ADMIN_PASSWORD` (Grafana refuses to start without it).

On a small VM (1–2 GB of RAM), remove `observability` from `COMPOSE_PROFILES`, then:

```bash
cd /opt/inmo24x7
./dc.sh --profile observability stop loki alloy grafana
```

Logs then stay in Docker only (`./dc.sh logs`, 10 MB × 5 per container), and the
backoffice hides its Grafana links when `GRAFANA_URL` is empty.

## Reaching Grafana

- **Published** (`GRAFANA_DOMAIN=grafana.<domain>` and its DNS record): Caddy serves it with
  HTTPS from `caddy/grafana.caddy`. `GRAFANA_ALLOWED_IPS` (space-separated IPs or CIDRs)
  answers 403 to everyone else; empty lets anyone reach the login page.
- **Not published** (`GRAFANA_DOMAIN` empty): Grafana listens only on the VM's
  `127.0.0.1:3000`. From your machine: `ssh -L 3000:127.0.0.1:3000 deploy@<vm-ip>`, then
  http://localhost:3000.

First login: `admin` / `GRAFANA_ADMIN_PASSWORD`, then change it (Profile → Change password).
Grafana's own data (users, the changed password) lives on the `grafana_data` volume.

## Memory and disk

| Service | Memory limit | Disk |
| --- | --- | --- |
| Loki | 512 MB | `loki_data`: the logs (below) |
| Grafana | 256 MB | `grafana_data`: a few MB |
| Alloy | 192 MB | `alloy_data`: read positions |

**Disk estimate, to check after a week** (`docker system df -v | grep loki_data`): at MVP
traffic the app writes roughly 150 MB of JSON a day (a request line per API call, a few lines
per job, Caddy's access log). Loki compresses log chunks about 10×, so ≈ 15 MB a day,
× 14 days ≈ 210 MB plus the index: budget **1 GB**. Each extra 10 busy businesses add about
30 MB of raw logs a day. If the disk grows faster, lower `LOKI_RETENTION_DAYS` (redeploy; the
compactor deletes the excess within hours) or the ingestion limits in `loki/config.yaml`
(4 MB/s, bursts of 8 MB: a runaway loop is cut there, not on the disk).

## Alerts (email to SUPPORT_EMAIL)

Grafana-managed rules in `observability/grafana/provisioning/alerting/rules.yaml`, checked
every minute, sent through the app's SMTP account (`SMTP_*`, from `ALERTS_EMAIL_FROM`):

| Rule | Fires when |
| --- | --- |
| Errores en la API o el worker | more than 5 error lines in 5 minutes |
| Jobs muertos | any `job_dead` in 5 minutes |
| Firmas de webhook rechazadas | more than 20 `whatsapp_signature_rejected` in 15 minutes |
| Sin webhooks de Meta | no `whatsapp_webhook` in 6 hours while the last health sweep counted connected numbers |

Test the contact point once: Alerting → Contact points → *soporte* → Test.

## Saved queries (Explore, datasource Loki)

```logql
# Errors in the last hour (set the time range to "Last 1 hour")
{environment="production", level="error"}

# Everything for one request: the "código de referencia" is its first 8 characters
{environment="production"} | json | request_id=~"1a2b3c4d.*"

# Everything for one business
{environment="production"} | json | tenant_id="<tenant uuid>"
```

The backoffice builds the last two for you: Errores → Buscar por código de referencia, and
S9 → Ver logs.

## Updating the images

The three images are pinned in `compose.prod.yml` (and `docker-compose.yml` for development).
To update: check the release notes (Loki's for config changes, Grafana's for breaking
changes in provisioning), change the tags, run CI (it validates the Loki and Alloy configs),
then deploy. Loki keeps its data across minor versions; Grafana migrates its own database on
start.

## Locally

```bash
uv run --all-packages python scripts/dev.py --observability
```

starts the same three services from `docker-compose.yml` (Grafana at http://localhost:3000,
admin / admin). The API and the worker run on the host, so `dev.py` copies their output to
`.dev-logs/` and a local Alloy config (`config.local.alloy`) tails those files. Choose the
environment `development` in the dashboard. The rehearsal (`deploy/rehearsal.md`) runs the
production configuration, with Grafana at https://grafana.localhost.
