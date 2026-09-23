#!/usr/bin/env bash
# hsf-intake.sh — non-interactive, hot-swappable directory/file intake
#
# The real friction this fixes: `usys clone <dir>` prompts interactively
# ("[1] Proceed / [2] Exclude sensitive / [3] Cancel") and PowerShell does
# not forward piped stdin into that nested bash prompt correctly — every
# call silently exits 1 instead of intaking anything (hit live 2026-09-22
# on pbm-consulting-website/). This script calls intake.sh directly via a
# real bash pipe, which does work, and reads PHOENIX_AUTH/PHOENIX_WORKER_URL/
# CLONEPOOL_DIR the same live way usys.ps1 does (Windows User env vars,
# never hardcoded — the exact drift class of bug that's already bitten
# this project three separate times).
#
# "Hot swappable": intake.sh's own versioning is content-hash-triggered —
# re-running this on a folder after files change just files a new version
# under the same hex, it does not need special handling here. Pulling a
# fresh copy back into a working directory (the actual "swap" a running
# system would want) is what `usys open <name>.lol` / `intake clone`
# already do, integrity-gated — this script is only the "commit what
# changed into the pool" half, not a reimplementation of hot-swap itself.
#
# Usage:
#   scripts/hsf-intake.sh <path> [<path> ...]
#   scripts/hsf-intake.sh sector2/apps/office pbm-consulting-website
#
# Cascading levels (folder -> sub-system -> system), per Jerry's own
# stated order: pass the folders first, then re-run this script pointed
# at their shared parent for the sub-system level, then (deliberately, as
# its own separate run — never bundled silently into this script) do a
# whole-repo pass the same way past sessions have: one deliberate,
# reviewed sweep, not an automatic side effect of a routine intake call.

set -euo pipefail

INTAKE_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/sector2/package-handler/intake.sh"

resolve_user_env() {
  local name="$1"
  local val="${!name:-}"
  if [[ -z "${val}" ]]; then
    val="$(powershell.exe -NoProfile -Command "[Environment]::GetEnvironmentVariable('${name}','User')" 2>/dev/null | tr -d '\r')"
  fi
  printf '%s' "${val}"
}

export PHOENIX_AUTH="$(resolve_user_env PHOENIX_AUTH)"
export PHOENIX_WORKER_URL="$(resolve_user_env PHOENIX_WORKER_URL)"

raw_pool_dir="$(resolve_user_env CLONEPOOL_DIR)"
# Forward slashes only — a literal Windows backslash path embedded raw
# into intake.sh's sidecar JSON is an invalid escape and aborts the run
# before D1/R2 sync ever happens (documented landmine, worked around here
# the same way usys.ps1 does it).
export CLONEPOOL_DIR="$(printf '%s' "${raw_pool_dir}" | sed -E 's#^([A-Za-z]):#/\L\1#; s#\\#/#g')"

if [[ -z "${PHOENIX_AUTH}" || -z "${PHOENIX_WORKER_URL}" || -z "${CLONEPOOL_DIR}" ]]; then
  echo "[hsf-intake] could not resolve PHOENIX_AUTH / PHOENIX_WORKER_URL / CLONEPOOL_DIR from the User environment — aborting" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: $(basename "$0") <path> [<path> ...]" >&2
  exit 1
fi

status=0
for target in "$@"; do
  echo "=== intaking: ${target} ==="
  if ! echo "1" | bash "${INTAKE_SH}" "${target}"; then
    echo "[hsf-intake] FAILED: ${target}" >&2
    status=1
  fi
done

exit "${status}"
