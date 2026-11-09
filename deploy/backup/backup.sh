#!/usr/bin/env bash
# Daily backup: pg_dump (custom format) → age (to a public key) → rclone to BACKUP_REMOTE.
# Keeps BACKUP_KEEP_DAILY daily and BACKUP_KEEP_WEEKLY weekly dumps. One log line; exits
# non-zero on any failure, so the systemd unit shows it as failed.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT (age public key) is required}"
: "${BACKUP_REMOTE:?BACKUP_REMOTE (rclone remote:path) is required}"
# In an rclone connection string a ":" ends the parameters, so "endpoint=https://host" cuts it
# at "https" ("Custom endpoint `https` was not a valid URI"). Give the host alone (rclone uses
# https), or quote the whole value: endpoint='https://host'.
if [[ "$BACKUP_REMOTE" =~ endpoint=https?: ]]; then
	printf '%s backup status=failed reason=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
		"BACKUP_REMOTE has endpoint=http(s):// unquoted; use endpoint=<host> (see .env.production.example)"
	exit 1
fi
keep_daily="${BACKUP_KEEP_DAILY:-14}"
keep_weekly="${BACKUP_KEEP_WEEKLY:-8}"

log() { printf '%s backup %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "status=failed reason=$*"; exit 1; }

# libpq does not understand SQLAlchemy's "+psycopg" driver suffix.
url="${DATABASE_URL/postgresql+psycopg:/postgresql:}"

started=$(date +%s)
client_major=$(pg_dump --version | sed -E 's/[^0-9]*([0-9]+).*/\1/')
server_major=$(psql "$url" -Atc "SHOW server_version_num" | cut -c1-2) ||
	fail "cannot reach the database"
if ((server_major > client_major)); then
	fail "server Postgres ${server_major} is newer than pg_dump ${client_major}: update the image"
fi

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
day=$(date -u +%Y-%m-%d)
file="$workdir/${day}.dump.age"

# Our data is all in the public schema; Supabase's own schemas (auth, storage, ...) are not
# ours to dump (see deploy/restore.md for what that means for a full recovery).
pg_dump "$url" --format=custom --schema=public --no-owner --no-privileges |
	age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" --output "$file" ||
	fail "pg_dump or age failed"
size=$(wc -c <"$file")
((size > 1024)) || fail "the encrypted dump is suspiciously small (${size} bytes)"

rclone copyto --quiet "$file" "${BACKUP_REMOTE}/daily/${day}.dump.age" ||
	fail "upload failed"
if [[ "$(date -u +%u)" == "7" ]]; then
	week=$(date -u +%G-W%V)
	rclone copyto --quiet "$file" "${BACKUP_REMOTE}/weekly/${week}.dump.age" ||
		fail "weekly upload failed"
fi

# Retention by age: N days of dailies, N weeks of weeklies.
prune() {
	local folder="$1" age="$2"
	# A folder that does not exist yet (no Sunday so far) has nothing to prune.
	rclone lsf --max-depth 1 "${BACKUP_REMOTE}/${folder}" >/dev/null 2>&1 || return 0
	rclone delete --quiet --min-age "$age" "${BACKUP_REMOTE}/${folder}"
}
prune daily "$((keep_daily + 1))d" || fail "pruning dailies failed"
prune weekly "$((keep_weekly * 7 + 1))d" || fail "pruning weeklies failed"

log "status=ok file=daily/${day}.dump.age bytes=${size} seconds=$(($(date +%s) - started)) postgres=${server_major}"
