#!/usr/bin/env bash
# Runs inside the backup image (restore.sh starts it): downloads one encrypted dump,
# decrypts it with the identity file mounted at /run/age/identity, restores it into
# RESTORE_URL and prints a smoke query. Never points at the production database.
set -euo pipefail

object="${1:?usage: restore-inside.sh <daily/YYYY-MM-DD.dump.age | weekly/...>}"
: "${BACKUP_REMOTE:?BACKUP_REMOTE is required}"
: "${RESTORE_URL:?RESTORE_URL (the scratch database) is required}"
identity=/run/age/identity
[[ -r "$identity" ]] || { echo "No age identity at $identity" >&2; exit 1; }

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
rclone copyto --quiet "${BACKUP_REMOTE}/${object}" "$workdir/dump.age"
age --decrypt --identity "$identity" --output "$workdir/dump" "$workdir/dump.age"
pg_restore --dbname "$RESTORE_URL" --clean --if-exists --no-owner --no-privileges \
	--exit-on-error "$workdir/dump"

psql "$RESTORE_URL" -At <<'SQL'
SELECT 'alembic ' || string_agg(version_num, ',') FROM alembic_version;
SELECT 'tenants ' || count(*) FROM tenants;
SELECT 'leads ' || count(*) FROM leads;
SELECT 'messages ' || count(*) FROM conversation_messages;
SQL
echo "restore ok: ${object}"
