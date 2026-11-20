#!/usr/bin/env bash
# Deploys one commit's images: pull, migrate once, start, wait for /health/ready, and roll
# back to the previous images if the new ones never get healthy. Idempotent: deploying the
# running commit again changes nothing.
#
#   ./deploy.sh <commit-sha>                 # images ${IMAGE_PREFIX}/inmo24x7-*:sha-<commit>
#                                            # (and cuentas-claras-* with its profile on)
#   ./deploy.sh <commit-sha> --local-images  # images already on this machine (the rehearsal):
#                                            # nothing is pulled
#
# Pulls: only our app images (inmo24x7-api/web/backoffice, and cuentas-claras-* with its
# profile on), one at a time, each with a timeout and one retry. Third-party images (Caddy,
# Loki, Alloy, Grafana) have pinned tags: they are pulled only when missing, so a version
# bump in compose.prod.yml still works. A pull that fails twice stops the deploy before
# anything is migrated or restarted.
#
# Every long step has a timeout per attempt (seconds; the environment overrides them) and
# is retried once when it runs out of time:
#   DEPLOY_PULL_TIMEOUT=300     each image pull
#   DEPLOY_MIGRATE_TIMEOUT=300  alembic upgrade heads (idempotent, so a retry is safe)
#   DEPLOY_UP_TIMEOUT=120       docker compose up (also the rollback's)
# Docker has been seen to hang intermittently on container creation (`compose run migrate`
# waiting minutes for POST /containers/create, a manual `docker create` right after working
# at once): on a timeout the compose process is killed, a leftover migrate-run container is
# removed, and the step runs again. A migration that fails (not a timeout) is not retried.
# The health wait (120 s) and rollback are unchanged. Worst case, about 26 minutes: the
# Deploy workflow's 30-minute job timeout is above it, so the script finishes (and rolls
# back) before GitHub cuts the SSH session.
#
# After a successful deploy, our app images other than the last 3 deployed tags (the
# history is in state/deployed_history) and dangling images are removed, and the space
# reclaimed is printed. Third-party images and images in use are never removed.
# DEPLOY_SKIP_PRUNE=1 skips it.
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

# `up` does not notice new content in bind-mounted config files (install-files.sh writes them
# in place): reload Caddy, restart the logs stack, when theirs changed since the last deploy.
config_changed() {
	local name="$1" hash
	shift
	hash="$(files_hash "$@")"
	[[ "$(cat "$state_dir/config_$name" 2>/dev/null || true)" != "$hash" ]] || return 1
	echo "$hash" >"$state_dir/config_$name"
}
apply_config_changes() {
	if config_changed caddy Caddyfile caddy; then
		say "Caddy configuration changed: reloading Caddy"
		compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile ||
			echo "Caddy did not reload: check './dc.sh logs caddy'." >&2
	fi
	if observability_enabled && config_changed observability observability; then
		say "Logs stack configuration changed: restarting Loki, Alloy and Grafana"
		compose restart loki alloy grafana ||
			echo "The logs stack did not restart: check './dc.sh ps'." >&2
	fi
}

pull_timeout="${DEPLOY_PULL_TIMEOUT:-300}"
migrate_timeout="${DEPLOY_MIGRATE_TIMEOUT:-300}"
up_timeout="${DEPLOY_UP_TIMEOUT:-120}"
for value in "$pull_timeout" "$migrate_timeout" "$up_timeout"; do
	[[ "$value" =~ ^[1-9][0-9]*$ ]] || {
		echo "DEPLOY_*_TIMEOUT must be a number of seconds, got: $value" >&2
		exit 2
	}
done
running="${current:-nothing}"
keeps_running="${current:-the current version}"
image_prefix="${IMAGE_PREFIX:-$(env_value IMAGE_PREFIX)}"

# Pulls one image with a timeout, and once more after a pause. Exits the deploy when both fail.
pull_image() {
	local image="$1" attempt status reason=""
	for attempt in 1 2; do
		status=0
		timeout --kill-after=15 "$pull_timeout" docker pull --quiet "$image" >/dev/null || status=$?
		((status == 0)) && return 0
		if timed_out "$status"; then
			reason="timed out after $pull_timeout s"
		else
			reason="failed (exit $status)"
		fi
		if ((attempt == 1)); then
			echo "Pull of $image $reason: retrying in 10 s." >&2
			sleep 10
		fi
	done
	echo "Pull of $image $reason; nothing was changed, $keeps_running keeps running." >&2
	exit 1
}

pull_images() {
	local images image
	images="$(compose config --images "${services[@]}" | sort -u)"
	while IFS= read -r image; do
		[[ -n "$image" ]] || continue
		if [[ -n "$image_prefix" && "$image" == "$image_prefix/"* ]]; then
			say "Pulling $image"
			pull_image "$image"
		elif docker image inspect "$image" >/dev/null 2>&1; then
			echo "    $image: already here (pinned tag), not pulled"
		else
			say "Pulling $image (pinned, not on this machine yet)"
			pull_image "$image"
		fi
	done <<<"$images"
}

# Starts the services with the given tag; on a timeout, once more (`up` is idempotent).
# Returns 124/137 when both attempts ran out of time.
start_version() {
	local attempt status
	for attempt in 1 2; do
		status=0
		IMAGE_TAG="$1" compose_within "$up_timeout" up -d --remove-orphans "${services[@]}" ||
			status=$?
		timed_out "$status" || return "$status"
		if ((attempt == 1)); then
			echo "'docker compose up' for $1 timed out after $up_timeout s: retrying in 5 s." >&2
			sleep 5
		fi
	done
	echo "'docker compose up' for $1 timed out twice ($up_timeout s each)." >&2
	return "$status"
}

# The one-off migrate containers (`<project>-migrate-run-<id>`) a killed `compose run` left.
remove_migrate_leftovers() {
	local ids
	ids="$(docker ps --all --quiet --filter "label=com.docker.compose.project=$COMPOSE_PROJECT" \
		--filter label=com.docker.compose.service=migrate \
		--filter label=com.docker.compose.oneoff=True 2>/dev/null || true)"
	if [[ -n "$ids" ]]; then
		echo "Removing the leftover migrate container(s): $(echo "$ids" | paste -sd ' ')" >&2
		# shellcheck disable=SC2086 # one id per word
		docker rm --force $ids >/dev/null 2>&1 || true
	fi
}

# alembic upgrade heads with a timeout; on a timeout, kill it, clean up and run it once more.
migrate() {
	local attempt status
	for attempt in 1 2; do
		status=0
		compose_within "$migrate_timeout" --profile tools run --rm migrate || status=$?
		((status == 0)) && return 0
		if ! timed_out "$status"; then
			echo "Migration failed: nothing was restarted, $keeps_running keeps running." >&2
			return 1
		fi
		# Give a create that dockerd was still finishing a moment to land, then remove it.
		sleep 5
		remove_migrate_leftovers
		if ((attempt == 1)); then
			echo "Migration timed out after $migrate_timeout s: retrying (alembic upgrade heads" \
				"is idempotent)." >&2
		fi
	done
	echo "Migration timed out twice ($migrate_timeout s each) and was stopped: nothing was" \
		"restarted, $keeps_running keeps running. Check './dc.sh --profile tools run --rm" \
		"migrate alembic current' before retrying." >&2
	return 1
}

# Keeps the last 3 deployed tags (and the one running before this deploy) of our app images;
# removes their older tags and the dangling images.
prune_images() {
	local history="$state_dir/deployed_history" keep line repository root before after
	if [[ "${DEPLOY_SKIP_PRUNE:-}" == 1 ]]; then
		say "Not pruning images (DEPLOY_SKIP_PRUNE=1)"
		return 0
	fi
	[[ -n "$image_prefix" ]] || return 0
	keep=" $(tail -n 3 "$history" | tr '\n' ' ')$current $(cat "$state_dir/previous_tag" 2>/dev/null || true) "
	root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
	before="$(df -B1 --output=used "$root" 2>/dev/null | tail -n 1 || true)"
	say "Pruning old app images (keeping$(tail -n 3 "$history" | sed 's/^/ /' | tr -d '\n'))"
	for repository in inmo24x7-api inmo24x7-web inmo24x7-backoffice \
		cuentas-claras-api cuentas-claras-web cuentas-claras-backoffice; do
		while IFS= read -r line; do
			[[ "$line" == *:sha-* ]] || continue
			[[ "$keep" == *" ${line##*:} "* ]] && continue
			# An image a container still uses (running or stopped) is refused: fine, it stays.
			if docker image rm "$line" >/dev/null 2>&1; then
				echo "    removed $line"
			fi
		done < <(docker image ls --format '{{.Repository}}:{{.Tag}}' "$image_prefix/$repository")
	done
	docker image prune --force >/dev/null || true
	after="$(df -B1 --output=used "$root" 2>/dev/null | tail -n 1 || true)"
	if [[ "$before" =~ ^\ *[0-9]+$ && "$after" =~ ^\ *[0-9]+$ ]] && ((before > after)); then
		say "Reclaimed $(numfmt --to=iec $((before - after)))"
	else
		say "Reclaimed nothing measurable"
	fi
}

record_deployed() {
	local history="$state_dir/deployed_history"
	if [[ -n "$current" && "$current" != "$tag" ]]; then
		echo "$current" >"$state_dir/previous_tag"
	fi
	echo "$tag" >"$state_dir/deployed_tag"
	# Most recent last, each tag once.
	{
		grep -vxF "$tag" "$history" 2>/dev/null || true
		echo "$tag"
	} | tail -n 20 >"$history.new"
	mv "$history.new" "$history"
}

export IMAGE_TAG="$tag"
say "Deploying $tag (running now: $running)"

if [[ "$local_images" == false ]]; then
	say "Pulling images (timeout $pull_timeout s each, one retry)"
	pull_images
else
	say "Using the images already on this machine (--local-images): nothing is pulled"
fi

ensure_backup_image

say "Migrating the database (alembic upgrade heads, timeout $migrate_timeout s, one retry)"
migrate || exit 1

say "Starting the new version (timeout $up_timeout s, one retry)"
up_status=0
start_version "$tag" || up_status=$?

if ! timed_out "$up_status" && wait_ready "$sha" 120; then
	record_deployed
	say "Deployed $tag: /health/ready reports commit $sha"
	apply_config_changes
	compose ps --format 'table {{.Service}}\t{{.Status}}'
	prune_images || echo "Pruning images failed (the deploy itself succeeded)." >&2
	exit 0
fi

if ! timed_out "$up_status"; then
	echo "The new version did not become ready within 120 s. Last API logs:" >&2
	compose logs --tail 40 api >&2 || true
fi

if [[ -z "$current" || "$current" == "$tag" ]]; then
	echo "No previous version to roll back to." >&2
	exit 1
fi

say "Rolling back to $current"
export IMAGE_TAG="$current"
rollback_status=0
start_version "$current" || rollback_status=$?
if ! timed_out "$rollback_status" && wait_ready "${current#sha-}" 120; then
	echo "Rolled back to $current. Migrations were NOT rolled back: the database stays at" \
		"the new revision, which the previous version must tolerate." >&2
else
	echo "Rollback to $current did not become ready either: check 'docker compose logs'." >&2
fi
exit 1
