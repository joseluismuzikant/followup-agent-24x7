# Backups and restore

## What is backed up

Every day at 06:00 UTC the `inmo24x7-backup.timer` runs `backup-now.sh`, which runs the
`backup` service (`deploy/backup/backup.sh`):

1. `pg_dump --format=custom --schema=public` of the Supabase database (pg_dump 17; it refuses a
   server newer than itself);
2. encrypted with `age` to `BACKUP_AGE_RECIPIENT` (a public key: the VM cannot decrypt);
3. uploaded with rclone to `BACKUP_REMOTE` (Oracle Object Storage, S3-compatible) as
   `daily/YYYY-MM-DD.dump.age`, and on Sundays also `weekly/YYYY-Www.dump.age`;
4. pruned to 14 dailies and 8 weeklies.

It logs one line (`status=ok … bytes=… seconds=…`) and exits non-zero on any failure:
`systemctl status inmo24x7-backup.service` and `journalctl -u inmo24x7-backup` show it.

Supabase's own backups do not replace this: they live in the same account as the database,
the Free plan has none, and point-in-time recovery is a paid add-on.

**What is not in the dump:** Supabase's own schemas (`auth`, `storage`, ...). Our profiles
use the Supabase user ids, so a full recovery restores this dump into the **same** Supabase
project (its users are still there). Recovering into a brand-new project also needs the
users moved over (Supabase's guide on migrating auth users) or everyone signing up again.

## Keys

Create the key pair on your machine, never on the VM:

```bash
age-keygen -o ~/inmo24x7-backup.agekey   # prints "Public key: age1..."
```

Put the public key in `.env.production` (`BACKUP_AGE_RECIPIENT`). Keep the identity file in
your password manager and an offline copy: without it no backup can be read.

## Restore a dump (into a scratch database)

On the VM (or any machine with the deploy folder, Docker and `.env.production`):

```bash
cd /opt/inmo24x7
./restore.sh latest ~/inmo24x7-backup.agekey                  # the newest daily
./restore.sh daily/2026-11-20.dump.age ~/inmo24x7-backup.agekey
```

It starts a throwaway Postgres 17 container, downloads and decrypts the dump, restores it
with `pg_restore`, prints the Alembic revision and row counts, and removes the container. It
never touches the production database. Copy the identity file to the VM only for the drill
and delete it afterwards (`shred -u`).

## The restore drill (once after go-live, then every few months)

1. Wait for the first backup (or run one now: `./backup-now.sh`).
2. `./restore.sh latest ~/inmo24x7-backup.agekey` → it ends with `restore ok`.
3. Check the numbers are plausible (tenants, leads, messages) and the Alembic revision is
   the deployed one.
4. Note the date and the duration in your ops notes. Delete the identity file from the VM.

## Restoring into production (disaster recovery)

Only after a real loss, with the app stopped (`docker compose --project-name inmo24x7
--env-file .env.production -f compose.prod.yml stop api worker`):
restore the chosen dump into the Supabase database with `pg_restore --clean --if-exists
--no-owner --no-privileges --dbname "<session pooler URL>"`, run `alembic upgrade heads`
(`docker compose ... run --rm migrate`), and start the app again. Practise it in the drill
first.
