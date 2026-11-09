#!/usr/bin/env bash
# docker compose for this deployment, with everything lib.sh computes (the deployed image tag,
# COMPOSE_PROFILES, the Caddy site files and Grafana's URL and cookie settings), so a manual
# `up` recreates nothing with the wrong settings:
#
#   ./dc.sh ps
#   ./dc.sh logs -f api worker
#   ./dc.sh up -d grafana
#   ./dc.sh run --rm api python scripts/make_admin.py <email> --create
#
# On the VM: alias dc=/opt/inmo24x7/dc.sh
set -euo pipefail

# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

if [[ "$IMAGE_TAG" == not-deployed ]]; then
	echo "Nothing deployed yet ($STATE_DIR/deployed_tag is missing): run ./deploy.sh <sha> first." >&2
	exit 1
fi
compose "$@"
