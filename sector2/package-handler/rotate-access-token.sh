#!/usr/bin/env bash
# ============================================================
# rotate-access-token.sh — Phoenix DevOps / UnitedSys
# Author: jwl247 / Phoenix DevOps LLC
# License: GPL-3.0
# ============================================================
# Rotates the Cloudflare Access service token `usys-cli` (CF_ACCESS_CLIENT_ID /
# CF_ACCESS_CLIENT_SECRET), the second lock in front of packages-worker (Security Gap 1).
# Jerry, 2026-10-07: "it needs added to the rotate list". Run by `rotate-key` after PHOENIX_AUTH.
#
# Cloudflare keeps the Client ID and issues a new Client Secret. The old secret stays valid
# for GRACE (1 h) so boxes can pull the new one from the vault; then Access revokes it.
# Legs, in order, stopping on the first failure:
#   1. Cloudflare API: rotate -> new secret (never printed)
#   2. prove the new secret: packages-worker /whoami with it -> 200
#   3. this PC (HKCU\Environment), 4. vault master files
#
# Needs, from the vault (F:\Phoenix\Vault\secrets\*.env), names only here:
#   CF_ACCESS_ROTATE_TOKEN  a Cloudflare API token on the jw.leftwich1 account with
#                           "Access: Service Tokens Write" and nothing else (Jerry makes it once)
#   CLOUDFLARE_ACCOUNT_ID, CF_ACCESS_CLIENT_ID, PHOENIX_AUTH
# Secrets travel through files and the environment, never a command line (A2-N1).
# ============================================================
set -euo pipefail

if [[ -n "${CLAUDECODE:-}${CLAUDE_CODE_ENTRYPOINT:-}" || ! -t 0 ]]; then
  echo "rotate-access-token: refused - Jerry runs this himself, in a terminal (rotate-key in PS7)"; exit 1
fi

VAULT_DIR="${PHOENIX_VAULT_SECRETS:-/f/Phoenix/Vault/secrets}"
WORKER_URL="${PHOENIX_WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
API="https://api.cloudflare.com/client/v4"
GRACE_SECONDS=3600

vault_get() {  # vault_get NAME -> value from the first non-template vault file that has it
  local f
  for f in "${VAULT_DIR}"/*; do
    [[ -f "$f" && "$f" != *.template ]] || continue
    grep -m1 "^$1=" "$f" 2>/dev/null | cut -d= -f2- && return 0
  done
  return 1
}

ROT="$(vault_get CF_ACCESS_ROTATE_TOKEN || true)"
ACCT="$(vault_get CLOUDFLARE_ACCOUNT_ID || true)"
CID="$(vault_get CF_ACCESS_CLIENT_ID || true)"
AUTH="$(vault_get PHOENIX_AUTH || true)"
[[ -n "$ROT" ]]  || { echo "  ABORTED - no CF_ACCESS_ROTATE_TOKEN in the vault. Make it once (dash.cloudflare.com > My Profile > API Tokens > Create Custom Token: Account / Access: Service Tokens / Edit, jw.leftwich1 account only) and add the line CF_ACCESS_ROTATE_TOKEN=... to the vault env file."; exit 1; }
[[ -n "$ACCT" && -n "$CID" && -n "$AUTH" ]] || { echo "  ABORTED - vault lacks CLOUDFLARE_ACCOUNT_ID, CF_ACCESS_CLIENT_ID or PHOENIX_AUTH"; exit 1; }

W="$(umask 077; mktemp -d)"; trap 'rm -rf "$W"' EXIT
printf 'Authorization: Bearer %s\n' "$ROT" > "$W/api"

# ── 1. find the token by its Client ID, then rotate ───────────────────────
curl -sf -H @"$W/api" "$API/accounts/$ACCT/access/service_tokens?per_page=100" > "$W/list" \
  || { echo "  ABORTED - Cloudflare refused the token list (check CF_ACCESS_ROTATE_TOKEN's permission)"; exit 1; }
TID="$(CID="$CID" python -c 'import json,os,sys
d=json.load(sys.stdin); m=[t for t in d.get("result") or [] if t.get("client_id")==os.environ["CID"]]
print(m[0]["id"] if m else "")' < "$W/list")"
[[ -n "$TID" ]] || { echo "  ABORTED - no Access service token with this Client ID on the account"; exit 1; }

EXP="$(python -c "import datetime as d;print((d.datetime.now(d.timezone.utc)+d.timedelta(seconds=$GRACE_SECONDS)).strftime('%Y-%m-%dT%H:%M:%SZ'))")"
printf '{"previous_client_secret_expires_at":"%s"}' "$EXP" > "$W/body"
curl -sf -X POST -H @"$W/api" -H "Content-Type: application/json" --data-binary @"$W/body" \
  "$API/accounts/$ACCT/access/service_tokens/$TID/rotate" > "$W/rot" \
  || { echo "  ABORTED - Cloudflare refused the rotation; nothing changed"; exit 1; }
python -c 'import json,sys; s=(json.load(sys.stdin).get("result") or {}).get("client_secret",""); sys.stdout.write(s)' < "$W/rot" > "$W/secret"
[[ -s "$W/secret" ]] || { echo "  ABORTED - Cloudflare answered without a new secret; the old one still works"; exit 1; }
NEW="$(cat "$W/secret")"
echo "  Cloudflare: new secret issued (old one valid until $EXP)"

# ── 2. prove it before anything local changes ─────────────────────────────
printf 'CF-Access-Client-Id: %s\nCF-Access-Client-Secret: %s\nAuthorization: Bearer %s\n' "$CID" "$NEW" "$AUTH" > "$W/hdr"
code="000"
for _ in 1 2 3 4 5 6; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H @"$W/hdr" "$WORKER_URL/whoami" || true)"
  [[ "$code" == "200" ]] && break; sleep 5
done
if [[ "$code" != "200" ]]; then
  echo "  ABORTED - packages-worker /whoami with the new secret -> $code. The OLD secret still works until $EXP;"
  echo "  this PC and the vault were NOT changed. Re-run rotate-key to try again."
  exit 1
fi
echo "  packages-worker accepts the new secret (/whoami -> 200)"

# ── 3. this PC (value through the environment, not argv) ──────────────────
NT="$NEW" powershell.exe -NoProfile -Command "[Environment]::SetEnvironmentVariable('CF_ACCESS_CLIENT_SECRET', \$env:NT, 'User')" \
  || { echo "  WARNING - Cloudflare + worker are on the new secret but this PC is not: set CF_ACCESS_CLIENT_SECRET by hand from the vault"; exit 1; }
echo "  this PC (HKCU\\Environment) updated"

# ── 4. vault master files ─────────────────────────────────────────────────
hits=0
while IFS= read -r vf; do
  ( umask 077; NT="$NEW" awk '/^CF_ACCESS_CLIENT_SECRET=/{print "CF_ACCESS_CLIENT_SECRET=" ENVIRON["NT"]; next} {print}' "$vf" > "$vf.rot.$$" ) \
    && mv "$vf.rot.$$" "$vf" && hits=$((hits + 1)) && echo "  vault: updated $(basename "$vf")"
done < <(grep -l '^CF_ACCESS_CLIENT_SECRET=' "${VAULT_DIR}"/* 2>/dev/null | grep -v '\.template$' || true)
[[ "$hits" -gt 0 ]] || echo "  vault: no CF_ACCESS_CLIENT_SECRET= line found in ${VAULT_DIR} - add it by hand"
echo "  Access token rotated. Boxes pick it up from the vault within the hour (old secret ends $EXP)."
