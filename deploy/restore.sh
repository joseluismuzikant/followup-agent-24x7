#!/usr/bin/env bash
# Restores one backup into a throwaway Postgres 17 container and runs a smoke query. Never
# touches the production database.
#
#   ./restore.sh daily/2026-11-20.dump.age ~/inmo24x7-backup.agekey
#   ./restore.sh latest ~/inmo24x7-backup.agekey      # the newest daily dump
set -euo pipefail

# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

[[ $# -eq 2 ]] || {
	echo "usage: restore.sh <daily/YYYY-MM-DD.dump.age | latest> <age-identity-file>" >&2
	exit 2
}
object="$1"
identity="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"
[[ -r "$identity" ]] || {
	echo "Cannot read the age identity file: $2" >&2
	exit 1
}

scratch="${COMPOSE_PROJECT}-restore-scratch"
network="${COMPOSE_PROJECT}_internal"
cleanup() { docker rm -f "$scratch" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [[ "$object" == "latest" ]]; then
	# shellcheck disable=SC2016 # expanded inside the container, where BACKUP_REMOTE is set
	object="daily/$(compose --profile tools run --rm -T --entrypoint sh backup \
		-c 'rclone lsf --files-only "$BACKUP_REMOTE/daily"' | sort | tail -n 1)"
	[[ "$object" != "daily/" ]] || {
		echo "No daily backups found." >&2
		exit 1
	}
fi

say "Starting a scratch Postgres 17"
cleanup
docker run -d --name "$scratch" --network "$network" \
	-e POSTGRES_PASSWORD=scratch postgres:17-alpine >/dev/null
for _ in $(seq 1 30); do
	docker exec "$scratch" pg_isready -U postgres >/dev/null 2>&1 && break
	sleep 1
done

say "Restoring $object"
compose --profile tools run --rm --user root \
	--entrypoint /usr/local/bin/restore-inside.sh \
	-v "$identity:/run/age/identity:ro" \
	-e "RESTORE_URL=postgresql://postgres:scratch@${scratch}:5432/postgres" \
	backup "$object"
say "Restore drill passed; the scratch database is removed on exit."
