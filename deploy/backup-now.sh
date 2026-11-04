#!/usr/bin/env bash
# Runs one backup now (the systemd timer calls this daily). See restore.md.
set -euo pipefail

# shellcheck source=SCRIPTDIR/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

compose --profile tools run --rm -T backup
