#!/usr/bin/env bash
# ============================================================
# rotate-phoenix-auth.sh — Phoenix DevOps / UnitedSys
# Author: jwl247 / Phoenix DevOps LLC
# License: GPL-3.0
# ============================================================
# PHOENIX_AUTH lives in three places that don't sync with each other:
#   1. Windows registry (HKCU\Environment, via setx)         — what intake.sh reads
#   2. packages-worker's Cloudflare secret                   — D1 + R2 sync
#   3. office-notify-worker's Cloudflare secret               — Office Module 3 tamper alerts
#   4. pbm-radar-worker's Cloudflare secret                   — Set-Aside Radar admin routes
# (phoenix-clonepool-r2 was a 4th leg until it was retired 2026-09-21 in favor
# of packages-worker's own integrated R2 handling — see sector2/package-handler/r2-worker/.)
# The 2026-08-21 and 2026-08-22 incidents were exactly this: one of the legs
# drifted from the others, and nothing noticed until sync had been silently
# broken for a while. This script is the only supported way to rotate the
# token — it pushes to every worker, verifies each via /whoami before moving
# on, and only touches the registry once all are confirmed live. If any
# step fails, it stops immediately and tells you exactly which leg is out of
# sync instead of leaving all of them in an unknown state.
#
# Usage: ./rotate-phoenix-auth.sh   (run from Git Bash — needs wrangler CLI
#         logged in, and setx.exe on PATH, which Git Bash gets from Windows)
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
D1_WORKER_DIR="${SCRIPT_DIR}/worker"
OFFICE_WORKER_DIR="${SCRIPT_DIR}/../apps/office/notify-worker"
D1_WORKER_URL="https://packages-worker.phoenix-jwl.workers.dev"
OFFICE_WORKER_URL="https://office-notify-worker.phoenix-jwl.workers.dev"
RADAR_WORKER_DIR="${SCRIPT_DIR}/../../pbm-consulting-website/radar-worker"
RADAR_WORKER_URL="https://pbm-radar-worker.phoenix-jwl.workers.dev"

command -v wrangler >/dev/null 2>&1 || { echo "wrangler CLI not found on PATH — install it first (npm i -g wrangler)"; exit 1; }
command -v setx >/dev/null 2>&1     || { echo "setx.exe not found — this must run under Windows/Git Bash"; exit 1; }
command -v curl >/dev/null 2>&1     || { echo "curl not found on PATH"; exit 1; }

[[ -n "${CF_ACCESS_CLIENT_ID:-}" && -n "${CF_ACCESS_CLIENT_SECRET:-}" ]] || {
  echo "CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET not set — packages-worker's"
  echo "/whoami check can't get past Cloudflare Access without them. Nothing touched."
  exit 1
}
[[ -d "${D1_WORKER_DIR}" ]] || { echo "missing ${D1_WORKER_DIR}"; exit 1; }
[[ -d "${OFFICE_WORKER_DIR}" ]] || { echo "missing ${OFFICE_WORKER_DIR}"; exit 1; }
[[ -d "${RADAR_WORKER_DIR}" ]] || { echo "missing ${RADAR_WORKER_DIR}"; exit 1; }

echo ""
echo "── Phoenix PHOENIX_AUTH rotation ──────────────────────────────"

NEW_TOKEN="$(openssl rand -hex 32)"
[[ -n "${NEW_TOKEN}" ]] || { echo "failed to generate a new token"; exit 1; }
echo "Generated a new 64-char token (not printed)."

# packages-worker's workers.dev hostname sits behind Cloudflare Access
# (2026-09-21, Gap 1 fix) — without the usys-cli service-token headers,
# /whoami gets a 302 to the Access login page, never a 200. Before this was
# added, every rotation pushed the new secret to packages-worker, then
# "failed" verification and aborted with the registry still on the OLD token
# — i.e. the script itself caused exactly the drift it exists to prevent.
# Headers go through a 0600 file, never curl's argv: anything on the command line
# is readable by every local process while it runs (A2-N1, S2CORE-S29).
HDR_FILE="$(mktemp)"; chmod 600 "${HDR_FILE}"
trap 'rm -f "${HDR_FILE}"' EXIT
{
  printf 'Authorization: Bearer %s\n' "${NEW_TOKEN}"
  [[ -n "${CF_ACCESS_CLIENT_ID:-}" ]] && printf 'CF-Access-Client-Id: %s\n' "${CF_ACCESS_CLIENT_ID}"
  [[ -n "${CF_ACCESS_CLIENT_SECRET:-}" ]] && printf 'CF-Access-Client-Secret: %s\n' "${CF_ACCESS_CLIENT_SECRET}"
} > "${HDR_FILE}"
check_whoami() {
  curl -s -o /dev/null -w "%{http_code}" -H @"${HDR_FILE}" "$1/whoami" 2>/dev/null || true
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

# ── packages-worker (D1 + R2) ──────────────────────────────────
push_secret "${D1_WORKER_DIR}" "packages-worker"
code="$(check_whoami_retry "${D1_WORKER_URL}")"
if [[ "${code}" != "200" ]]; then
  echo ""
  echo "  ABORTED — packages-worker did not accept the new token (/whoami → ${code})."
  echo "  Nothing else was touched: the registry still has the OLD token."
  exit 1
fi
echo "  packages-worker verified (/whoami → 200)"

# ── office-notify-worker (Office Module 3) ────────────────────
push_secret "${OFFICE_WORKER_DIR}" "office-notify-worker"
code="$(check_whoami_retry "${OFFICE_WORKER_URL}")"
if [[ "${code}" != "200" ]]; then
  echo ""
  echo "  ABORTED — office-notify-worker did not accept the new token (/whoami → ${code})."
  echo "  WARNING: packages-worker is ALREADY on the NEW token, but this one and"
  echo "  the registry are still on the OLD token. Re-run this script to finish"
  echo "  — do not hand-edit anything, that's how they drift."
  exit 1
fi
echo "  office-notify-worker verified (/whoami → 200)"

# ── pbm-radar-worker (Set-Aside Radar) ────────────────────────
push_secret "${RADAR_WORKER_DIR}" "pbm-radar-worker"
code="$(check_whoami_retry "${RADAR_WORKER_URL}")"
if [[ "${code}" != "200" ]]; then
  echo ""
  echo "  ABORTED — pbm-radar-worker did not accept the new token (/whoami → ${code})."
  echo "  WARNING: packages-worker and office-notify-worker are ALREADY on the NEW"
  echo "  token, but this one and the registry are still on the OLD token. Re-run"
  echo "  this script to finish — do not hand-edit anything, that's how they drift."
  exit 1
fi
echo "  pbm-radar-worker verified (/whoami → 200)"

# ── Only now touch the local registry value ───────────────────
setx PHOENIX_AUTH "${NEW_TOKEN}" >/dev/null
export PHOENIX_AUTH="${NEW_TOKEN}"

# ── The vault master copy (boxes pull PHOENIX_AUTH from it) ───────────────
# Before 2026-10-07 a rotation left the vault on the OLD key, so the next box
# to `phoenix_vault.py pull` got a dead token. The value goes in through the
# environment (awk ENVIRON), never argv.
VAULT_DIR="${PHOENIX_VAULT_SECRETS:-/f/Phoenix/Vault/secrets}"
vault_hits=0
if [[ -d "${VAULT_DIR}" ]]; then
  while IFS= read -r vf; do
    ( umask 077; NT="${NEW_TOKEN}" awk '/^PHOENIX_AUTH=/{print "PHOENIX_AUTH=" ENVIRON["NT"]; next} {print}' "${vf}" > "${vf}.rot.$$" ) \
      && mv "${vf}.rot.$$" "${vf}" && vault_hits=$((vault_hits + 1)) && echo "  vault: updated $(basename "${vf}")"
  done < <(grep -l '^PHOENIX_AUTH=' "${VAULT_DIR}"/* 2>/dev/null | grep -v '\.template$' || true)   # never a real key into a template
fi
[[ "${vault_hits}" == "0" ]] && echo "  vault: no PHOENIX_AUTH= line found in ${VAULT_DIR} - update it by hand"
echo "  Registry (HKCU\\Environment) updated for this Windows user."

echo ""
echo "── Done — all worker legs verified and in sync ──────────────────────"
echo "This Git Bash session already has the new token exported."
echo "Any OTHER already-open terminal (PowerShell, another Git Bash) needs to"
echo "be closed and reopened to pick up the new registry value — that's a"
echo "normal Windows env-var limitation, not a rotation failure."
echo ""
echo "LAST STEP - the cloud copy of the vault (boxes pull from it):"
echo "  PBMII, PowerShell 7:  cd F:\Phoenix\Phoenix-DevOps-oS ; python scripts\phoenix_vault.py push"
echo "  then on any box that holds the key:  python3 phoenix_vault.py pull --keys PHOENIX_AUTH,PHOENIX_WORKER_URL --dest /etc/phoenix/secrets"
echo ""
