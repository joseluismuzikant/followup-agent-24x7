#!/usr/bin/env bash
# Installs one release's deploy files into the app directory. The Deploy workflow uploads
# deploy/ at the commit it deploys to <app>/releases/<sha>/ and runs this script from there,
# before deploy.sh:
#
#   bash /opt/inmo24x7/releases/<sha>/install-files.sh [--github]
#
# Only the paths listed below are written. .env.production, state/, releases/ and anything
# else in the app directory are never touched. Files are overwritten in place (same inode),
# so the single-file bind mounts of running containers (Caddyfile, Loki, Alloy) see the new
# content; deploy.sh then reloads or restarts what changed. Keeps the last 5 releases.
# --github prints warnings as GitHub Actions annotations.
set -euo pipefail

release="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_dir="${APP_DIR:-$(dirname "$(dirname "$release")")}"
github=false
[[ "${1:-}" == "--github" ]] && github=true

SCRIPTS=(deploy.sh lib.sh backup-now.sh restore.sh dc.sh install-files.sh)
FILES=(compose.prod.yml Caddyfile)
# Read inside the Caddy, Loki, Alloy and Grafana containers (their own users): world-readable,
# no secrets in them. backup/ is the backup image's build context.
DIRS=(caddy observability backup)
KEEP_RELEASES=5

say() { printf '==> %s\n' "$*"; }
warn() {
	if [[ "$github" == true ]]; then
		printf '::warning::%s\n' "$*"
	else
		printf 'WARNING: %s\n' "$*" >&2
	fi
}

[[ "$(basename "$(dirname "$release")")" == releases ]] || {
	echo "Run this from <app>/releases/<sha>/, not from $release." >&2
	exit 1
}
[[ -d "$app_dir" && -w "$app_dir" ]] || {
	echo "Cannot write to the app directory $app_dir (run as its owner, deploy)." >&2
	exit 1
}
for path in "${SCRIPTS[@]}" "${FILES[@]}" "${DIRS[@]}"; do
	[[ -e "$release/$path" ]] || {
		echo "The release has no $path: nothing was installed." >&2
		exit 1
	}
done
if [[ -n "$(find "$release" -name '.env*' -print -quit)" ]]; then
	echo "The release contains an environment file: nothing was installed." >&2
	exit 1
fi

changed=()
# Copies one file in place (cp truncates and rewrites the existing inode) and sets its mode.
put() {
	local source="$1" target="$2" mode="$3"
	if ! cmp -s "$source" "$target" 2>/dev/null; then
		mkdir -p "$(dirname "$target")"
		cp "$source" "$target"
		changed+=("${target#"$app_dir"/}")
	fi
	chmod "$mode" "$target"
}

say "Installing the deploy files of $(basename "$release") into $app_dir"
for file in "${SCRIPTS[@]}"; do
	put "$release/$file" "$app_dir/$file" 750
done
for file in "${FILES[@]}"; do
	put "$release/$file" "$app_dir/$file" 644
done
for dir in "${DIRS[@]}"; do
	while IFS= read -r -d '' source; do
		put "$source" "$app_dir/$dir/${source#"$release/$dir/"}" 644
	done < <(find "$release/$dir" -type f -print0)
	# Files the release no longer has.
	while IFS= read -r -d '' target; do
		if [[ ! -e "$release/$dir/${target#"$app_dir/$dir/"}" ]]; then
			rm -f "$target"
			changed+=("${target#"$app_dir"/} (removed)")
		fi
	done < <(find "$app_dir/$dir" -type f -print0)
	find "$app_dir/$dir" -mindepth 1 -type d -empty -delete
	find "$app_dir/$dir" -type d -exec chmod 755 {} +
done
# The backup image's entrypoints (copied into the image with these modes).
chmod 755 "$app_dir"/backup/*.sh
if [[ $EUID -eq 0 ]]; then
	chown -R deploy:deploy "${SCRIPTS[@]/#/$app_dir/}" "${FILES[@]/#/$app_dir/}" \
		"${DIRS[@]/#/$app_dir/}"
fi
if ((${#changed[@]})); then
	printf '    changed: %s\n' "${changed[@]}"
else
	echo "    no changes"
fi

# The systemd units need root: never installed from here, only compared.
for unit in "$release"/systemd/*; do
	name="$(basename "$unit")"
	if ! cmp -s "$unit" "/etc/systemd/system/$name"; then
		warn "systemd/$name differs from /etc/systemd/system/$name. On the VM run:" \
			"sudo install -m 644 $unit /etc/systemd/system/ && sudo systemctl daemon-reload"
	fi
done

say "Keeping the last $KEEP_RELEASES releases"
touch "$release"
# Release folders are named by commit sha (hex only), so plain globbing is safe.
mapfile -t releases < <(ls -1dt "$app_dir"/releases/*/)
for old in "${releases[@]:$KEEP_RELEASES}"; do
	rm -rf "$old"
	echo "    removed $(basename "$old")"
done
