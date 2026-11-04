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

`smoke` checks, in order:

1. `https://api.localhost/health/ready` reports the deployed commit;
2. the panel and backoffice load, with HSTS and the CSP that allows the Facebook SDK;
3. every table has row level security, and the Alembic revision;
4. a Supabase token (ES256, verified with the JWKS and the issuer) signs up; `make_admin.py`
   runs in the API container; a confirmed email joins the business an admin created for it,
   and an unconfirmed one never does;
5. a signed webhook goes through Caddy, the worker answers with the agent's reply, and a bad
   signature gets 401;
6. a backup runs and `restore.sh latest` restores it into a scratch database.

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

Sign in at https://app.localhost with a magic link: the email is in the Supabase CLI's mail
UI (http://127.0.0.1:54324). `supabase/config.toml` lists `https://app.localhost` and
`https://admin.localhost` as redirect URLs; restart the CLI stack (`npx supabase stop &&
npx supabase start`) if it was running before you pulled that change. Make yourself an
admin with:

```bash
docker compose --project-name inmo24x7-rehearsal --project-directory deploy \
  -f deploy/compose.prod.yml -f deploy/rehearsal/compose.rehearsal.yml \
  --env-file deploy/rehearsal/.env.rehearsal \
  run --rm api python scripts/make_admin.py <your email>
```
