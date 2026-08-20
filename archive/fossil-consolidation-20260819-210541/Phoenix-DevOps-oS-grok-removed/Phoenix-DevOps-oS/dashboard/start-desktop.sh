#!/usr/bin/env bash
# start-desktop.sh — Launch Phoenix desktop with ~/.phoenix/phoenix.env loaded
# Used by systemd (phoenix-dashboard.service) and manual Linux starts.

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

ENV_FILE="${PHOENIX_ENV_FILE:-$HOME/.phoenix/phoenix.env}"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi

export PHOENIX_SKIP_AUTH_MODAL="${PHOENIX_SKIP_AUTH_MODAL:-1}"

exec npm start