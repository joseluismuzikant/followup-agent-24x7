#!/usr/bin/env bash
# Deploys one commit's images: pull, migrate once, start, wait for /health/ready, and roll
# back to the previous images if the new ones never get healthy. Idempotent: deploying the
# running commit again changes nothing.
#
#   ./deploy.sh <commit-sha>                 # images ${IMAGE_PREFIX}/inmo24x7-*:sha-<commit>
#                                            # (and cuentas-claras-* with its profile on)
#   ./deploy.sh <commit-sha> --local-images  # images already on this machine (the rehearsal)
#
# Migrations are never rolled back: they must stay compatible with the previous version
# (expand first, remove in a later deploy; see ARCHITECTURE.md, "Migrations").
set -euo pipefail

# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

usage() {
	echo "usage: deploy.sh <commit-sha> [--local-images]" >&2
	exit 2
}

[[ $# -ge 1 ]] || usage
sha="$1"
local_images=false
[[ "${2:-}" == "--local-images" ]] && local_images=true
[[ "$sha" =~ ^[0-9a-f]{7,40}(-dirty)?$ ]] || {
	echo "Not a commit sha: $sha" >&2
	usage
}

tag="sha-${sha}"
state_dir="$STATE_DIR"
mkdir -p "$state_dir"
current="$(cat "$state_dir/deployed_tag" 2>/dev/null || true)"
services=(api worker web backoffice caddy)
if observability_enabled; then
	services+=(loki alloy grafana)
fi
if cuentas_claras_enabled; then
	services+=(cc-api cc-worker cc-web cc-backoffice)
fi

export IMAGE_TAG="$tag"
say "Deploying $tag (running now: ${current:-nothing})"

if [[ "$local_images" == false ]]; then
	say "Pulling images"
	compose pull "${services[@]}"
fi

ensure_backup_image

say "Migrating the database (alembic upgrade heads)"
if ! compose --profile tools run --rm migrate; then
	echo "Migration failed: nothing was restarted, ${current:-the current version} keeps running." >&2
	exit 1
fi

say "Starting the new version"
compose up -d --remove-orphans "${services[@]}" || true

if wait_ready "$sha" 120; then
	if [[ -n "$current" && "$current" != "$tag" ]]; then
		echo "$current" >"$state_dir/previous_tag"
	fi
	echo "$tag" >"$state_dir/deployed_tag"
	say "Deployed $tag: /health/ready reports commit $sha"
	compose ps --format 'table {{.Service}}\t{{.Status}}'
	exit 0
fi

echo "The new version did not become ready within 120 s. Last API logs:" >&2
compose logs --tail 40 api >&2 || true

if [[ -z "$current" || "$current" == "$tag" ]]; then
	echo "No previous version to roll back to." >&2
	exit 1
fi

say "Rolling back to $current"
export IMAGE_TAG="$current"
compose up -d --remove-orphans "${services[@]}" || true
if wait_ready "${current#sha-}" 120; then
	echo "Rolled back to $current. Migrations were NOT rolled back: the database stays at" \
		"the new revision, which the previous version must tolerate." >&2
else
	echo "Rollback to $current did not become ready either: check 'docker compose logs'." >&2
fi
exit 1
