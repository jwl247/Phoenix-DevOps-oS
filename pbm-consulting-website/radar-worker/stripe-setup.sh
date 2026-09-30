#!/usr/bin/env bash
# stripe-setup.sh — wire Set-Aside Radar's $9.99/month into Stripe, then into the worker.
#
#   bash stripe-setup.sh test     # sandbox first
#   bash stripe-setup.sh live     # the real one, after the test run checks out
#
# Creates (once per mode; re-running reuses what exists):
#   product "Set-Aside Radar" -> $9.99/month price -> Payment Link
#   webhook endpoint -> <worker>/stripe/webhook (checkout.session.completed,
#                       customer.subscription.updated, customer.subscription.deleted)
# then sets worker secrets STRIPE_PAYMENT_LINK + STRIPE_WEBHOOK_SECRET, applies
# schema.sql to pbm_radar_db (CREATE IF NOT EXISTS only) and deploys.
#
# The Stripe key is read from the vault drop file and never printed or put on a
# command line (curl reads it from stdin via -K -; audit A2-N1).
# Key names looked for:  test -> STRIPE_SECRET_KEY, stripe_secret_key
#                        live -> STRIPE_SECRET_KEY_LIVE, stripe_secret_key_live
# Override with STRIPE_KEY_NAME=... and STRIPE_KEY_FILE=...
set -euo pipefail

MODE="${1:-}"
[[ "$MODE" == test || "$MODE" == live ]] || { echo "usage: bash stripe-setup.sh test|live" >&2; exit 2; }
cd "$(dirname "$0")"

WORKER_URL="https://pbm-radar-worker.phoenix-jwl.workers.dev"
HOOK_URL="$WORKER_URL/stripe/webhook"
FILES=("${STRIPE_KEY_FILE:-}" "F:/Phoenix/Vault/secrets/NEW-TOKEN-DROP.env" "F:/Phoenix/Vault/secrets/phoenix-secrets.env")
if [[ "$MODE" == test ]]; then NAMES=(STRIPE_SECRET_KEY stripe_secret_key); PREFIX=_test_; else NAMES=(STRIPE_SECRET_KEY_LIVE stripe_secret_key_live); PREFIX=_live_; fi
[[ -n "${STRIPE_KEY_NAME:-}" ]] && NAMES=("$STRIPE_KEY_NAME")

SK=""
for f in "${FILES[@]}"; do
  [[ -n "$f" && -f "$f" ]] || continue
  for n in "${NAMES[@]}"; do
    v="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${n}[[:space:]]*=" "$f" | tail -1 | sed -E 's/^[^=]*=[[:space:]]*//; s/^["'\'']//; s/["'\'']?[[:space:]]*$//' | tr -d '\r')" || true
    if [[ -n "$v" ]]; then SK="$v"; echo "key: $n from $(basename "$f")"; break 2; fi
  done
done
[[ -n "$SK" ]] || { echo "no Stripe key found (looked for ${NAMES[*]}); set STRIPE_KEY_NAME / STRIPE_KEY_FILE" >&2; exit 1; }
[[ "$SK" == sk${PREFIX}* || "$SK" == rk${PREFIX}* ]] || { echo "that key is not a ${MODE}-mode key (expected sk${PREFIX}...); refusing" >&2; exit 1; }

# stripe METHOD PATH [form args...]  -> JSON on stdout; key via stdin config, never argv.
stripe() {
  local method="$1" path="$2"; shift 2
  local args=()
  for a in "$@"; do args+=(--data-urlencode "$a"); done
  local get=(); [[ "$method" == GET ]] && get=(-G)   # GET: form args go in the query string
  printf 'user = "%s:"\n' "$SK" | curl -sS -K - "${get[@]}" -X "$method" "https://api.stripe.com/v1/$path" "${args[@]}"
}
# jget EXPR [ARG] — print a Python expression over the JSON reply `d` (A = ARG).
# EXPR is always a literal written in this script, never data; Stripe's reply is
# only ever parsed with json.load, and outside values come in through ARG.
jget() { python -c "import sys,json;d=json.load(sys.stdin);A=sys.argv[2] if len(sys.argv)>2 else '';e=d.get('error');sys.exit('stripe: '+e.get('message','error')) if e else print(eval(sys.argv[1]))" "$@"; }

# Product (reuse by metadata tag)
PROD="$(stripe GET "products/search" "query=metadata['pbm_app']:'radar' AND active:'true'" | jget "(d['data'][0]['id'] if d['data'] else '')")"
if [[ -z "$PROD" ]]; then
  PROD="$(stripe POST products "name=Set-Aside Radar" "description=Matched federal set-aside bids by email, hand-reviewed. PBM Consulting Service." "metadata[pbm_app]=radar" | jget "d['id']")"
  echo "product: created $PROD"
else echo "product: reusing $PROD"; fi

# $9.99/month price
PRICE="$(stripe GET "prices?product=$PROD&active=true&limit=100" | jget "next((p['id'] for p in d['data'] if p['unit_amount']==999 and p['currency']=='usd' and (p.get('recurring') or {}).get('interval')=='month'),'')")"
if [[ -z "$PRICE" ]]; then
  PRICE="$(stripe POST prices "product=$PROD" unit_amount=999 currency=usd "recurring[interval]=month" | jget "d['id']")"
  echo "price: created $PRICE"
else echo "price: reusing $PRICE"; fi

# Payment Link (reuse by metadata tag)
LINK="$(stripe GET "payment_links?active=true&limit=100" | jget "next((l['url'] for l in d['data'] if (l.get('metadata') or {}).get('pbm_app')=='radar'),'')")"
if [[ -z "$LINK" ]]; then
  LINK="$(stripe POST payment_links "line_items[0][price]=$PRICE" "line_items[0][quantity]=1" "metadata[pbm_app]=radar" \
    "after_completion[type]=hosted_confirmation" \
    "after_completion[hosted_confirmation][custom_message]=Thank you. Set-Aside Radar keeps watching SAM.gov for you every weekday morning. Questions: reply to any Radar email." \
    | jget "d['url']")"
  echo "payment link: created $LINK"
else echo "payment link: reusing $LINK"; fi

# Webhook endpoint. Stripe only reveals the signing secret at creation, so an
# existing endpoint is replaced (deleted + recreated) to get a secret we can store.
OLD="$(stripe GET "webhook_endpoints?limit=100" | jget "' '.join(w['id'] for w in d['data'] if w['url']==A)" "$HOOK_URL")"
for w in $OLD; do stripe DELETE "webhook_endpoints/$w" >/dev/null; echo "webhook: replaced old $w"; done
HOOK_JSON="$(stripe POST webhook_endpoints "url=$HOOK_URL" "description=Set-Aside Radar billing" \
  "enabled_events[]=checkout.session.completed" "enabled_events[]=customer.subscription.updated" "enabled_events[]=customer.subscription.deleted")"
WHSEC="$(printf '%s' "$HOOK_JSON" | jget "d['secret']")"
echo "webhook: created $(printf '%s' "$HOOK_JSON" | jget "d['id']") -> $HOOK_URL"

NPX=npx; command -v npx.cmd >/dev/null 2>&1 && NPX=npx.cmd
printf '%s' "$LINK"  | "$NPX" wrangler secret put STRIPE_PAYMENT_LINK
printf '%s' "$WHSEC" | "$NPX" wrangler secret put STRIPE_WEBHOOK_SECRET
unset SK WHSEC
"$NPX" wrangler d1 execute pbm_radar_db --remote --file=schema.sql
"$NPX" wrangler deploy

echo
echo "check: curl -s $WORKER_URL/health   (stripe_payment_link: $MODE, stripe_webhook: set)"
