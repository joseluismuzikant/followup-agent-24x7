#!/usr/bin/env bash
# Shared by deploy.sh, restore.sh and the rehearsal. Sourced, never run.
#   COMPOSE_FILES  space-separated compose files, relative to deploy/ (default: compose.prod.yml)
#   ENV_FILE       the environment file, relative to deploy/ (default: .env.production)
#   COMPOSE_PROJECT the compose project name (default: inmo24x7)
#   COMPOSE_PROFILES  compose profiles (default: COMPOSE_PROFILES from the environment file)

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILES="${COMPOSE_FILES:-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-inmo24x7}"
# deploy.sh records what it deployed here (state/ for production, state-rehearsal/ ...).
STATE_DIR="$DEPLOY_DIR/state${COMPOSE_PROJECT#inmo24x7}"
# Compose needs an image tag even for one-off services: default to the deployed one.
IMAGE_TAG="${IMAGE_TAG:-$(cat "$STATE_DIR/deployed_tag" 2>/dev/null || echo not-deployed)}"

# One value from the environment file (empty when it is missing).
env_value() {
	local file="$DEPLOY_DIR/$ENV_FILE"
	[[ -f "$file" ]] || return 0
	sed -n "s/^$1=//p" "$file" | tail -n 1
}

# COMPOSE_PROFILES=observability in the environment file turns on Loki, Alloy and Grafana.
COMPOSE_PROFILES="${COMPOSE_PROFILES:-$(env_value COMPOSE_PROFILES)}"
# Grafana is published by Caddy only when GRAFANA_DOMAIN is set; otherwise an SSH tunnel.
grafana_domain="$(env_value GRAFANA_DOMAIN)"
if [[ -n "$grafana_domain" ]]; then
	CADDY_GRAFANA_SITE="./caddy/grafana.caddy"
	GRAFANA_ROOT_URL="https://$grafana_domain"
	GRAFANA_COOKIE_SECURE=true
else
	CADDY_GRAFANA_SITE="./caddy/no-grafana.caddy"
	GRAFANA_ROOT_URL="http://localhost:3000"
	GRAFANA_COOKIE_SECURE=false
fi

observability_enabled() {
	[[ ",$COMPOSE_PROFILES," == *",observability,"* ]]
}

# COMPOSE_PROFILES=cuentas-claras turns on Cuentas Claras's services and Caddy's three hosts.
cuentas_claras_enabled() {
	[[ ",$COMPOSE_PROFILES," == *",cuentas-claras,"* ]]
}
if cuentas_claras_enabled; then
	CADDY_CUENTAS_CLARAS_SITE="./caddy/cuentas-claras.caddy"
else
	CADDY_CUENTAS_CLARAS_SITE="./caddy/no-cuentas-claras.caddy"
fi
export ENV_FILE IMAGE_TAG COMPOSE_PROJECT COMPOSE_PROFILES CADDY_GRAFANA_SITE GRAFANA_ROOT_URL \
	GRAFANA_COOKIE_SECURE CADDY_CUENTAS_CLARAS_SITE

compose_args=(--project-name "$COMPOSE_PROJECT" --project-directory "$DEPLOY_DIR"
	--env-file "$DEPLOY_DIR/$ENV_FILE")
for compose_file in $COMPOSE_FILES; do
	compose_args+=(-f "$DEPLOY_DIR/$compose_file")
done
unset compose_file

compose() {
	docker compose "${compose_args[@]}" "$@"
}

# Runs `docker compose ...` for at most $1 seconds (SIGTERM, then SIGKILL 15 s later).
# Returns 124 when it ran out of time (137 when it also had to be killed).
# stdin is /dev/null: `timeout` puts compose in a background process group, and from an
# interactive SSH session a compose that touches the terminal (a `run` allocating a TTY) is
# stopped by the kernel (SIGTTIN/SIGTTOU) and never runs. Not `timeout --foreground`: it
# would no longer kill compose on a timeout, which the retries rely on.
compose_within() {
	local seconds="$1"
	shift
	timeout --kill-after=15 "$seconds" docker compose "${compose_args[@]}" "$@" </dev/null
}

timed_out() { [[ "$1" == 124 || "$1" == 137 ]]; }

say() { printf '==> %s\n' "$*"; }

# A hash of the files under the given paths (relative to deploy/), to notice changes.
files_hash() {
	(cd "$DEPLOY_DIR" && find "$@" -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum |
		cut -d' ' -f1)
}

# The backup image is built on this machine (deploy/backup), not pulled: build it when it is
# missing or when deploy/backup changed since it was built (deploy.sh, backup-now.sh and
# restore.sh call this).
ensure_backup_image() {
	local image="${BACKUP_IMAGE:-$(env_value BACKUP_IMAGE)}" hash built
	image="${image:-inmo24x7-backup:local}"
	hash="$(files_hash backup)"
	built="$(cat "$STATE_DIR/backup_image_hash" 2>/dev/null || true)"
	if ! docker image inspect "$image" >/dev/null 2>&1 || [[ "$built" != "$hash" ]]; then
		say "Building the backup image ($image)"
		compose --profile tools build backup
		mkdir -p "$STATE_DIR"
		echo "$hash" >"$STATE_DIR/backup_image_hash"
	fi
}

# The commit /health/ready reports, or nothing while the API is not ready.
ready_commit() {
	compose exec -T api python -c '
import json, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8001/health/ready", timeout=4) as response:
    print(json.load(response)["commit"])
' 2>/dev/null || true
}

# Waits up to $2 seconds (default 120) for /health/ready to report commit $1.
wait_ready() {
	local expected="$1" deadline=$((SECONDS + ${2:-120})) commit
	while ((SECONDS < deadline)); do
		commit="$(ready_commit)"
		if [[ "$commit" == "$expected" ]]; then
			return 0
		fi
		sleep 3
	done
	return 1
}
