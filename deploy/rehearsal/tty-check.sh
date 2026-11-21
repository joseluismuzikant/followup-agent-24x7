#!/usr/bin/env bash
# deploy.sh run by hand from an interactive terminal must not stop at the migration.
#
#   deploy/rehearsal/tty-check.sh            # checks this tree's deploy.sh and lib.sh
#   TTY_CHECK_FROM=<dir> tty-check.sh        # checks the deploy.sh and lib.sh in <dir>
#
# It runs the real deploy.sh inside a pseudo-terminal (`script`), with a fake `docker` on
# PATH; no Docker daemon is needed. Like the real `docker compose run` without -T, the fake
# configures the terminal when its stdin is one: from the background process group that
# `timeout` creates, the kernel stops it (SIGTTOU) and the migration never runs. The check
# passes when the deploy finishes and the migrate `run` had -T and no terminal on stdin.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
from="${TTY_CHECK_FROM:-$here/..}"
sha=0000000
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail() {
	echo "tty-check: $*" >&2
	if [[ -f "$work/typescript" ]]; then
		echo "--- deploy.sh output:" >&2
		tr -d '\r' <"$work/typescript" >&2
	fi
	exit 1
}

command -v script >/dev/null || fail "'script' (util-linux) is required."

# A copy of what deploy.sh reads, so its state directory stays in the scratch directory.
mkdir -p "$work/deploy" "$work/bin"
cp "$from/deploy.sh" "$from/lib.sh" "$work/deploy/"
cp -r "$here/../backup" "$here/../caddy" "$here/../observability" "$here/../Caddyfile" \
	"$work/deploy/"

cat >"$work/bin/docker" <<'FAKE'
#!/usr/bin/env bash
# Fake docker for tty-check.sh: every call succeeds; `compose run` is logged.
if [[ "${1:-}" == compose ]]; then
	case " $* " in
	*" run "*)
		if [[ -t 0 ]]; then
			stty sane # what compose does with a TTY: stopped here when in the background
			stdin=terminal
		else
			stdin=not-a-terminal
		fi
		echo "stdin=$stdin args=$*" >>"$TTY_CHECK_LOG"
		;;
	*" exec "*" api "*) echo "$TTY_CHECK_SHA" ;;
	esac
fi
exit 0
FAKE
chmod +x "$work/bin/docker"

export PATH="$work/bin:$PATH"
export TTY_CHECK_LOG="$work/runs.log" TTY_CHECK_SHA="$sha"
export COMPOSE_PROJECT=inmo24x7-ttycheck ENV_FILE=.env.ttycheck COMPOSE_FILES=compose.prod.yml
export COMPOSE_PROFILES="" IMAGE_PREFIX="" DEPLOY_SKIP_PRUNE=1
# Short enough that a stopped migration fails the check quickly, through both attempts.
export DEPLOY_MIGRATE_TIMEOUT=10 DEPLOY_UP_TIMEOUT=10
touch "$TTY_CHECK_LOG"

status=0
printf -v command '%q %q --local-images' "$work/deploy/deploy.sh" "$sha"
timeout 90 script --quiet --return --command "$command" "$work/typescript" \
	</dev/null >/dev/null || status=$?

if ((status != 0)); then
	fail "deploy.sh exited $status from a terminal (124: it hung)."
fi
grep -q "Deployed sha-$sha" "$work/typescript" || fail "deploy.sh did not report the deploy."
migrate="$(grep -E ' run .* migrate' "$TTY_CHECK_LOG" || true)"
[[ -n "$migrate" ]] || fail "the migration never ran (stopped by the terminal?)."
[[ " $migrate " == *" run --rm -T "* ]] || fail "the migrate run has no -T: $migrate"
[[ "$migrate" == stdin=not-a-terminal* ]] || fail "the migrate run had a terminal on stdin."
echo "tty-check: deploy.sh from a terminal finished; the migrate run had -T and no terminal."
