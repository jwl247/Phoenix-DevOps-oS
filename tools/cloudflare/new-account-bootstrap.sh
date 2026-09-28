#!/usr/bin/env bash
# new-account-bootstrap.sh — stand Phoenix's package handler up in ANOTHER
# Cloudflare account (the jerry.leftwich1 account, 2026-09-28): D1 database
# from schema.sql, R2 bucket, packages-worker deployed, PHOENIX_AUTH set.
# Nothing in the repo is repointed: the test and the tools use
# PHOENIX_WORKER_URL, so the main account keeps working untouched.
#
#   CLOUDFLARE_API_TOKEN=<token for THAT account, Workers+D1+R2 edit> \
#   CLOUDFLARE_ACCOUNT_ID=<that account's id> \
#   tools/cloudflare/new-account-bootstrap.sh
#
# Prints the worker URL and writes the generated PHOENIX_AUTH to the file
# named by PHOENIX_AUTH_OUT (default: ./phoenix-auth.<account>.txt, mode 600)
# — move it into the vault (F:\Phoenix\Vault\secrets\), never into the repo.
# Cloudflare Access for the new workers.dev host is NOT created here (it is
# an account-level dashboard/API step; until it exists PHOENIX_AUTH is the
# only gate on that host — say so in the run-sheet).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
W="$ROOT/sector2/package-handler/worker"
: "${CLOUDFLARE_API_TOKEN:?set CLOUDFLARE_API_TOKEN for the target account}"
: "${CLOUDFLARE_ACCOUNT_ID:?set CLOUDFLARE_ACCOUNT_ID (the target account, NOT the main one)}"
export CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID
DB=phoenix_dev_db; BUCKET=phoenix-clonepool; NAME=packages-worker
WR="npx --yes wrangler@latest"

echo "== account $CLOUDFLARE_ACCOUNT_ID: whoami"
$WR whoami 2>&1 | grep -iE "account|email" | head -3

echo "== D1: $DB"
if ! $WR d1 list --json 2>/dev/null | python3 -c "import json,sys; sys.exit(0 if any(d.get('name')=='$DB' for d in json.load(sys.stdin)) else 1)"; then
  $WR d1 create "$DB" >/dev/null
fi
DB_ID=$($WR d1 list --json | python3 -c "import json,sys; print(next(d['uuid'] for d in json.load(sys.stdin) if d.get('name')=='$DB'))")
echo "   id $DB_ID"
$WR d1 execute "$DB" --remote --file="$W/schema.sql" >/dev/null
echo "   schema applied ($(grep -c 'CREATE TABLE' "$W/schema.sql") tables)"

echo "== R2: $BUCKET"
$WR r2 bucket list 2>/dev/null | grep -q "^name: *$BUCKET$\|\"name\": *\"$BUCKET\"\|^$BUCKET$" || $WR r2 bucket create "$BUCKET" >/dev/null
echo "   ok"

echo "== deploy $NAME (temp config with this account's database id)"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cp "$W/index.js" "$TMP/"
python3 - "$W/wrangler.jsonc" "$TMP/wrangler.jsonc" "$DB_ID" "$CLOUDFLARE_ACCOUNT_ID" <<'PY'
import re, sys
src, dst, db_id, acct = sys.argv[1:]
s = open(src).read()
s = re.sub(r'"database_id":\s*"[^"]+"', f'"database_id":   "{db_id}"', s)
s = s.replace('"name": "packages-worker",', f'"name": "packages-worker",\n  "account_id": "{acct}",')
open(dst, "w").write(s)
PY
( cd "$TMP" && $WR deploy --config wrangler.jsonc 2>&1 | grep -iE "deployed|https://|error" )
SUB=$($WR whoami 2>/dev/null | grep -oE '[a-z0-9-]+\.workers\.dev' | head -1 || true)
URL="https://$NAME.${SUB:-<subdomain>.workers.dev}"

echo "== PHOENIX_AUTH"
AUTH=$(python3 -c "import secrets; print(secrets.token_hex(32))")
OUT="${PHOENIX_AUTH_OUT:-$ROOT/phoenix-auth.$CLOUDFLARE_ACCOUNT_ID.txt}"
( umask 077; printf '%s\n' "$AUTH" > "$OUT" )
( cd "$TMP" && printf '%s' "$AUTH" | $WR secret put PHOENIX_AUTH --config wrangler.jsonc >/dev/null )
echo "   set on the worker; local copy: $OUT (move it to the vault)"

echo
echo "worker: $URL"
echo "check : curl -s -H \"Authorization: Bearer \$(cat $OUT)\" $URL/whoami"
echo "test  : PHOENIX_WORKER_URL=$URL PHOENIX_AUTH=\$(cat $OUT) tools/cloudflare/pull-run-test.sh"
