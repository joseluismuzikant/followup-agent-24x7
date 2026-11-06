# The local production rehearsal

Before the first real deploy, run the production setup on your machine: the same
`compose.prod.yml`, `deploy.sh`, migrations, Caddy, worker, backup and restore, with
`APP_ENV=production`. Deploy, migration and proxy problems show up here first.

What is different from production:

| Production | Rehearsal |
| --- | --- |
| Supabase Postgres | a local Postgres 17 container (`db`, published on 127.0.0.1:55432) |
| Supabase Auth | the local Supabase CLI stack (`npx supabase start`) |
| Let's Encrypt on your domains | Caddy's own CA on `api.localhost`, `app.localhost`, `admin.localhost` |
| GHCR images from CI | images built from your working tree, tagged `sha-<HEAD>` (`-dirty` with uncommitted changes) |
| SMTP provider | Mailpit (http://127.0.0.1:58025) |
| Grafana at `grafana.<domain>` | the same Loki + Alloy + Grafana at https://grafana.localhost (admin / `GRAFANA_ADMIN_PASSWORD` in `rehearsal/.env.rehearsal`) |
| Oracle Object Storage | a local volume (`BACKUP_REMOTE=:local:/backups`) |
| a real model, the Cloud API | the fake model and the log sender, allowed only by `REHEARSAL=true` |

`REHEARSAL=true` only works with `APP_ENV=production` and relaxes exactly two checks (an
empty `LLM_MODEL` and `WHATSAPP_SENDER=log`). It never appears in `.env.production.example`,
and `AUTH_MODE=dev` stays refused.

## Run it

Needs Docker, Node (for `npx`), `uv`, `openssl`, `curl`, and ports 80/443 free.

```bash
npx supabase start                    # repository root; prints the local keys
deploy/rehearsal/rehearsal.sh up      # builds the images, runs deploy.sh, starts everything
deploy/rehearsal/rehearsal.sh smoke   # end-to-end checks (below)
deploy/rehearsal/rehearsal.sh down    # removes containers, volumes and generated files
npx supabase stop
```

`up` writes `deploy/rehearsal/.env.rehearsal` from `supabase status` (git-ignored, deleted
by `down`): `SUPABASE_URL=http://127.0.0.1:54321` (the token issuer, as the browser sees
it), `SUPABASE_SERVER_URL` and `SUPABASE_JWKS_URL` through `host.docker.internal` (how the
API container reaches it), generated secrets, and a throwaway age key pair for the backup.
Ports 80/443 busy? `REHEARSAL_HTTP_PORT=8080 REHEARSAL_HTTPS_PORT=8443` (then add the port
to the URLs).

It builds the images locally and needs none of the GitHub repository variables (those only
gate CI's image publishing). `REHEARSAL_PRODUCTS=inmo24x7,cuentas-claras` also builds and
starts Cuentas Claras (profile `cuentas-claras`) at https://cuentasclaras.localhost,
https://cuentasclaras-admin.localhost and https://cuentasclaras-api.localhost; the smoke
checks still cover inmo24x7 only.

`smoke` checks, in order:

1. `https://api.localhost/health/ready` reports the deployed commit;
2. the panel and backoffice load, with HSTS and the CSP that allows the Facebook SDK;
3. every table has row level security, and the Alembic revision;
4. `make_admin.py --create` makes the first admin in Supabase Auth (service-role key); its
   temporary password signs in (ES256, verified with the JWKS and the issuer) but gets
   `password_change_required` until it is changed; "Dar de alta un negocio" gives an invited
   owner a temporary password, and after choosing her own she joins her business; Supabase
   refuses self sign-up;
5. a signed webhook goes through Caddy, the worker answers with the agent's reply, and a bad
   signature gets 401;
6. the API's webhook line and the worker's lines for that business (by `tenant_id`) reach
   Loki through Alloy, and Grafana answers at https://grafana.localhost;
7. a backup runs and `restore.sh latest` restores it into a scratch database.

## In the browser

Caddy signs the `.localhost` certificates with its own local CA. Either accept the warning
once per host, or trust the CA:

```bash
docker compose --project-name inmo24x7-rehearsal --project-directory deploy \
  -f deploy/compose.prod.yml -f deploy/rehearsal/compose.rehearsal.yml \
  --env-file deploy/rehearsal/.env.rehearsal \
  cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-rehearsal-root.crt
```

and import `caddy-rehearsal-root.crt` as a trusted authority (Chrome: Settings → Privacy →
Security → Manage certificates → Authorities; Firefox: Settings → Certificates → Import;
Linux system-wide: copy to `/usr/local/share/ca-certificates/` and run
`sudo update-ca-certificates`). Remove it after the rehearsal.

Nobody can sign up (as in production), so make yourself an admin first; it prints a
temporary password you change at the first sign-in at https://admin.localhost.
`supabase/config.toml` lists the rehearsal hosts as redirect URLs and turns sign-up off;
restart the CLI stack (`npx supabase stop && npx supabase start`) if it was running before
you pulled that change. Supabase's own emails ("¿Olvidaste tu clave?") are in the CLI's mail
UI (http://127.0.0.1:54324).

```bash
docker compose --project-name inmo24x7-rehearsal --project-directory deploy \
  -f deploy/compose.prod.yml -f deploy/rehearsal/compose.rehearsal.yml \
  --env-file deploy/rehearsal/.env.rehearsal \
  run --rm api python scripts/make_admin.py <your email> --create
```
