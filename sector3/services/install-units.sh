#!/usr/bin/env bash
# Phoenix systemd unit installer — explicit allow-list.
# Run as root: sudo ./install-units.sh <unit> [<unit> ...]
#
# Rewritten 2026-09-29 (S34OPS-F34 / F03). The old zsh version copied every
# unit in this directory blind (including the DASHBOARD_DIR / OLLAMA_BIN
# templates and the frank3 modprobe units) and then aborted on
# `systemctl enable phoenix-log-setup.service`, a unit that does not exist.
#
# Now: nothing is installed unless you name it, and only units whose
# ExecStart target really exists in the repo layout are accepted.
#
#   Allowed (ExecStart target exists):
#     helix.service                 -> /opt/phoenix/sector1/kernels/helix_boot.sh
#     phoenix-paging.service        -> /opt/phoenix/sector4/paging.py   (bare-metal box, e.g. pbm-compaq)
#     phoenix-helix-kernel.service  -> /phoenix/Phoenix-DevOps-oS/sector4/paging.py (Debian VM over the SMB share)
#   (phoenix-paging and phoenix-helix-kernel both run paging.py — pick one per box.)
#
#   Not installable here, on purpose:
#     phoenix-dashboard.service, phoenix-ollama.service, phoenix-desktop.target
#         templates (DASHBOARD_DIR / OLLAMA_BIN placeholders) — installed by deploy-dashboard.sh
#     frank3-slot-a.service, frank3-slot-b.service
#         kernel-module loading; needs Jerry's decision (S34OPS-F05)
#     phoenix-auto-config, -frankenhelix, -frank-helix, -intent-parser, -propagator,
#     -mega-security, -unoserver, -doc-worker, -scheduler .service,
#     phoenix-sector1.target, phoenix-sector2.target
#         ExecStart targets missing or mis-pathed under /home/jwl247/projects/phoenix (S34OPS-F04)

set -euo pipefail

UNIT_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ALLOWED=(helix.service phoenix-paging.service phoenix-helix-kernel.service)

usage() {
    echo "Usage: sudo $(basename "$0") <unit> [<unit> ...]"
    echo "Allowed units: ${ALLOWED[*]}"
    echo "(See the header of this script for why the others are excluded.)"
}

is_allowed() {
    local u="$1" a
    for a in "${ALLOWED[@]}"; do [[ "$a" == "$u" ]] && return 0; done
    return 1
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

# Validate everything before touching the system.
units=()
for u in "$@"; do
    if ! is_allowed "$u"; then
        echo "[install-units] refused: '$u' is not on the allow-list." >&2
        usage >&2
        exit 1
    fi
    [[ -f "$SCRIPT_DIR/$u" ]] || { echo "[install-units] missing unit file: $SCRIPT_DIR/$u" >&2; exit 1; }
    units+=("$u")
done
if [[ " ${units[*]} " == *" phoenix-paging.service "* && " ${units[*]} " == *" phoenix-helix-kernel.service "* ]]; then
    echo "[install-units] refused: phoenix-paging.service and phoenix-helix-kernel.service both run paging.py — pick one." >&2
    exit 1
fi
[[ $EUID -eq 0 ]] || { echo "[install-units] run as root (sudo)." >&2; exit 1; }

echo "Installing Phoenix systemd units: ${units[*]}"
for u in "${units[@]}"; do
    echo "  -> $u"
    install -m 644 "$SCRIPT_DIR/$u" "$UNIT_DIR/$u"
done

systemctl daemon-reload
for u in "${units[@]}"; do
    systemctl enable "$u"
done

echo ""
echo "Done. Start with: sudo systemctl start ${units[*]}"
echo "Status:           systemctl status ${units[*]}"
echo "Logs:             journalctl -u '${units[0]}' -f"
