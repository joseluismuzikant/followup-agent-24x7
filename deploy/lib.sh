#!/usr/bin/env bash
# Shared by deploy.sh, restore.sh and the rehearsal. Sourced, never run.
#   COMPOSE_FILES  space-separated compose files, relative to deploy/ (default: compose.prod.yml)
#   ENV_FILE       the environment file, relative to deploy/ (default: .env.production)
#   COMPOSE_PROJECT the compose project name (default: inmo24x7)

DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILES="${COMPOSE_FILES:-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-inmo24x7}"
# deploy.sh records what it deployed here (state/ for production, state-rehearsal/ ...).
STATE_DIR="$DEPLOY_DIR/state${COMPOSE_PROJECT#inmo24x7}"
# Compose needs an image tag even for one-off services: default to the deployed one.
IMAGE_TAG="${IMAGE_TAG:-$(cat "$STATE_DIR/deployed_tag" 2>/dev/null || echo not-deployed)}"
export ENV_FILE IMAGE_TAG

compose() {
	local args=(--project-name "$COMPOSE_PROJECT" --project-directory "$DEPLOY_DIR"
		--env-file "$DEPLOY_DIR/$ENV_FILE")
	local file
	for file in $COMPOSE_FILES; do
		args+=(-f "$DEPLOY_DIR/$file")
	done
	docker compose "${args[@]}" "$@"
}

say() { printf '==> %s\n' "$*"; }

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
