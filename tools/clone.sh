#!/usr/bin/env bash
# ============================================================
# Phoenix Global Clone -- clone.sh
# USys -- United Systems | jwl247 -- GPL v3
# Place in: Phoenix-DevOps-oS/tools/clone.sh
# ============================================================
# Forwarder only: runs bin/clone, the one clone engine (OUT of the pool).
#
# Why: until 2026-10-07 this file was the old IN command
# (`clone <file> [category] ["tag"]` = intake) and told Linux users to
# symlink it as /usr/local/bin/clone, while bin/clone, clone.cmd and
# `usys clone` take files OUT (changed 10-02/10-06, d68007f). A box set up
# from this file got the opposite meaning (audit CMDWALK-F06). Now every
# `clone` is OUT. To put something INTO the pool: `intake <file-or-folder>`.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLONE="$SCRIPT_DIR/../bin/clone"
[[ -f "$CLONE" ]] || CLONE="${PHOENIX_ROOT:-/nonexistent}/bin/clone"
[[ -f "$CLONE" ]] || { echo "[clone] bin/clone not found -- set PHOENIX_ROOT to your Phoenix-DevOps-oS checkout" >&2; exit 1; }

exec bash "$CLONE" "$@"
