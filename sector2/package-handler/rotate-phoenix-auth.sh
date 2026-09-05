#!/usr/bin/env bash
# ============================================================
# rotate-phoenix-auth.sh — Phoenix DevOps / UnitedSys
# Author: jwl247 / Phoenix DevOps LLC
# License: GPL-3.0
# ============================================================
# PHOENIX_AUTH lives in three places that don't sync with each other:
#   1. Windows registry (HKCU\Environment, via setx)         — what intake.sh reads
#   2. packages-worker's Cloudflare secret                   — D1 sync
#   3. phoenix-clonepool-r2's Cloudflare secret               — R2 sync
# The 2026-08-21 and 2026-08-22 incidents were exactly this: one of the three
# drifted from the others, and nothing noticed until sync had been silently
# broken for a while. This script is the only supported way to rotate the
# token — it pushes to both workers, verifies each via /whoami before moving
# on, and only touches the registry once both are confirmed live. If any
# step fails, it stops immediately and tells you exactly which leg is out of
# sync instead of leaving all three in an unknown state.
#
# Usage: ./rotate-phoenix-auth.sh   (run from Git Bash — needs wrangler CLI
#         logged in, and setx.exe on PATH, which Git Bash gets from Windows)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
D1_WORKER_DIR="${SCRIPT_DIR}/worker"
R2_WORKER_DIR="${SCRIPT_DIR}/r2-worker"
D1_WORKER_URL="https://packages-worker.phoenix-jwl.workers.dev"
R2_WORKER_URL="https://phoenix-clonepool-r2.phoenix-jwl.workers.dev"

command -v wrangler >/dev/null 2>&1 || { echo "wrangler CLI not found on PATH — install it first (npm i -g wrangler)"; exit 1; }
command -v setx >/dev/null 2>&1     || { echo "setx.exe not found — this must run under Windows/Git Bash"; exit 1; }
command -v curl >/dev/null 2>&1     || { echo "curl not found on PATH"; exit 1; }

[[ -d "${D1_WORKER_DIR}" ]] || { echo "missing ${D1_WORKER_DIR}"; exit 1; }
[[ -d "${R2_WORKER_DIR}" ]] || { echo "missing ${R2_WORKER_DIR}"; exit 1; }

echo ""
echo "── Phoenix PHOENIX_AUTH rotation ──────────────────────────────"

NEW_TOKEN="$(openssl rand -hex 32)"
[[ -n "${NEW_TOKEN}" ]] || { echo "failed to generate a new token"; exit 1; }
echo "Generated a new 64-char token (not printed)."

check_whoami() {
  curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${NEW_TOKEN}" \
    "$1/whoami" 2>/dev/null
}

# Cloudflare secret writes can take a few seconds to reach every edge —
# retry briefly before declaring a real mismatch.
check_whoami_retry() {
  local url="$1" code attempt
  for attempt in 1 2 3 4 5; do
    code="$(check_whoami "${url}")"
    [[ "${code}" == "200" ]] && { echo "200"; return 0; }
    sleep 2
  done
  echo "${code}"
}

push_secret() {
  local dir="$1" name="$2"
  echo "Pushing to ${name}..."
  ( cd "${dir}" && printf '%s' "${NEW_TOKEN}" | wrangler secret put PHOENIX_AUTH >/dev/null )
}

# ── packages-worker (D1) ──────────────────────────────────────
push_secret "${D1_WORKER_DIR}" "packages-worker"
code="$(check_whoami_retry "${D1_WORKER_URL}")"
if [[ "${code}" != "200" ]]; then
  echo ""
  echo "  ABORTED — packages-worker did not accept the new token (/whoami → ${code})."
  echo "  Nothing else was touched: the registry and phoenix-clonepool-r2 still"
  echo "  have the OLD token, and are still consistent with each other."
  exit 1
fi
echo "  packages-worker verified (/whoami → 200)"

# ── phoenix-clonepool-r2 (R2) ─────────────────────────────────
push_secret "${R2_WORKER_DIR}" "phoenix-clonepool-r2"
code="$(check_whoami_retry "${R2_WORKER_URL}")"
if [[ "${code}" != "200" ]]; then
  echo ""
  echo "  ABORTED — phoenix-clonepool-r2 did not accept the new token (/whoami → ${code})."
  echo "  WARNING: packages-worker is ALREADY on the NEW token, but this one and"
  echo "  the registry are still on the OLD token. Re-run this script to finish"
  echo "  — do not hand-edit anything, that's how they drift."
  exit 1
fi
echo "  phoenix-clonepool-r2 verified (/whoami → 200)"

# ── Only now touch the local registry value ───────────────────
setx PHOENIX_AUTH "${NEW_TOKEN}" >/dev/null
export PHOENIX_AUTH="${NEW_TOKEN}"
echo "  Registry (HKCU\\Environment) updated for this Windows user."

echo ""
echo "── Done — all three legs verified and in sync ─────────────────"
echo "This Git Bash session already has the new token exported."
echo "Any OTHER already-open terminal (PowerShell, another Git Bash) needs to"
echo "be closed and reopened to pick up the new registry value — that's a"
echo "normal Windows env-var limitation, not a rotation failure."
echo ""
