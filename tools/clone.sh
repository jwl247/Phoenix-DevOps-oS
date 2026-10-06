#!/usr/bin/env bash
# ============================================================
# Phoenix Global Clone -- clone.sh
# USys -- United Systems | jwl247
# Place in: Phoenix-DevOps-oS/tools/clone.sh
# Make global: sudo ln -s ~/Phoenix/Phoenix-DevOps-oS/tools/clone.sh /usr/local/bin/clone
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# -- Find intake.sh
INTAKE_SH="${PHOENIX_INTAKE:-}"
# A stale PHOENIX_INTAKE (moved/deleted path) falls back to the repo copy
# instead of stopping with "not found" (2026-10-02: it pointed at a dead D: path).
[[ -n "$INTAKE_SH" && ! -f "$INTAKE_SH" ]] && INTAKE_SH=""

if [[ -z "$INTAKE_SH" ]]; then
    for candidate in \
        "$REPO_ROOT/sector2/package-handler/intake.sh" \
        "$HOME/Phoenix/Phoenix-DevOps-oS/sector2/package-handler/intake.sh"
    # (standalone Phoenix-Package_handler candidates removed — that repo keeps
    #  intake.sh at its root and was archived 2026-09-13; S34OPS-F41)
    do
        if [[ -f "$candidate" ]]; then
            INTAKE_SH="$(realpath "$candidate")"
            break
        fi
    done
fi

if [[ -z "$INTAKE_SH" || ! -f "$INTAKE_SH" ]]; then
    echo ""
    echo "  clone: ERROR -- intake.sh not found"
    echo "  Options:"
    echo "    export PHOENIX_INTAKE=/path/to/intake.sh"
    echo "    or run from inside a Phoenix-DevOps-oS checkout (sector2/package-handler/intake.sh)"
    echo ""
    exit 1
fi

# -- Env defaults
export CLONEPOOL_DIR="${CLONEPOOL_DIR:-$HOME/Phoenix/clonepool}"
[[ -z "${PHOENIX_AUTH:-}" ]]       && echo "  clone: WARNING -- PHOENIX_AUTH not set. D1 sync skipped."
[[ -z "${PHOENIX_WORKER_URL:-}" ]] && echo "  clone: WARNING -- PHOENIX_WORKER_URL not set. D1 sync skipped."

# -- Usage
usage() {
cat << 'USAGE'

  Phoenix Clone -- global bash shim
  USys -- United Systems

  Usage:
    clone <file> [category] ["tag"]
    clone backend <name> <manager> <version>
    clone status
    clone --dry-run <file>
    clone help

  Examples:
    clone ./franken.py
    clone ./nginx.conf configs "production nginx"
    clone backend nodejs winget 20.11.0
    clone --dry-run ./myfile.sh

USAGE
}

# -- Flags
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && { DRY_RUN=1; shift; }
[[ $# -eq 0 || "${1:-}" == "help" || "${1:-}" == "--help" ]] && { usage; exit 0; }

# -- Dry run
if [[ $DRY_RUN -eq 1 ]]; then
    echo ""
    echo "  [DRY RUN] Phoenix Clone"
    echo "  File    : ${1}"
    echo "  Intake  : $INTAKE_SH"
    echo "  Args    : $*"
    echo "  Pool    : $CLONEPOOL_DIR"
    echo ""
    exit 0
fi

# -- Execute
echo ""
echo "  Phoenix Clone -> ${1}"
bash "$INTAKE_SH" "$@"

STATUS=$?
if [[ $STATUS -eq 0 ]]; then
    echo "  Cloned OK"
else
    echo "  clone failed (exit $STATUS)"
    exit $STATUS
fi
echo ""
