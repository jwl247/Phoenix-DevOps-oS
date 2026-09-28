#!/usr/bin/env bash
# setup-radar.sh — one-time Stripe setup for Set-Aside Radar, idempotent.
# Creates (or finds) the product and the $9.99/month price, registers the
# webhook endpoint, and prints exactly which secrets/vars to set on the
# worker. Test mode with a sk_test_ key, live mode with sk_live_. Never
# writes the key anywhere.
#
#   STRIPE_SECRET_KEY=sk_test_... tools/stripe/setup-radar.sh
#   STRIPE_SECRET_KEY=sk_live_... tools/stripe/setup-radar.sh     (after the bank account + LLC)
set -euo pipefail
# The keys live at the bottom of the vault's phoenix-secrets.env (Jerry,
# 2026-09-28) — the one spot every tool reads. Source it when the key is
# not already in the environment (Git Bash path first, then the drive letter).
if [[ -z "${STRIPE_SECRET_KEY:-}" ]]; then
  for f in "${PHOENIX_SECRETS_ENV:-}" /f/Phoenix/Vault/secrets/phoenix-secrets.env F:/Phoenix/Vault/secrets/phoenix-secrets.env; do
    [[ -n "$f" && -f "$f" ]] && { set -a; . "$f"; set +a; break; }
  done
fi
: "${STRIPE_SECRET_KEY:?STRIPE_SECRET_KEY not set and not found in the vault env file (F:\\Phoenix\\Vault\\secrets\\phoenix-secrets.env)}"
API=https://api.stripe.com/v1
WORKER="${WORKER_PUBLIC_URL:-https://pbm-radar-worker.phoenix-jwl.workers.dev}"
MODE=test; [[ "$STRIPE_SECRET_KEY" == sk_live_* ]] && MODE=live
s() { curl -sS -u "$STRIPE_SECRET_KEY:" -H 'Stripe-Version: 2024-06-20' "$@"; }
jq_() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1]))" "$1"; }

echo "== Stripe ($MODE mode): product"
PRODUCT_ID=$(s "$API/products/search" --get --data-urlencode "query=metadata['phoenix']:'set-aside-radar'" | jq_ "d['data'][0]['id'] if d['data'] else ''")
if [[ -z "$PRODUCT_ID" ]]; then
  PRODUCT_ID=$(s "$API/products" -d name="Set-Aside Radar" -d "description=Every morning: the federal set-aside bids that match your NAICS, certifications and states. One short email. PBM Consulting Service." \
    -d "metadata[phoenix]=set-aside-radar" -H "Idempotency-Key: radar-product-v1" | jq_ "d['id']")
  echo "   created $PRODUCT_ID"
else
  echo "   exists  $PRODUCT_ID"
fi

echo "== price: \$9.99 / month"
PRICE_ID=$(s "$API/prices" --get -d product="$PRODUCT_ID" -d active=true -d limit=10 | jq_ "next((p['id'] for p in d['data'] if p.get('unit_amount')==999 and p.get('recurring',{}).get('interval')=='month'), '')")
if [[ -z "$PRICE_ID" ]]; then
  PRICE_ID=$(s "$API/prices" -d product="$PRODUCT_ID" -d unit_amount=999 -d currency=usd -d "recurring[interval]=month" \
    -d "nickname=Set-Aside Radar monthly" -H "Idempotency-Key: radar-price-999-v1" | jq_ "d['id']")
  echo "   created $PRICE_ID"
else
  echo "   exists  $PRICE_ID"
fi

echo "== add-on price: Grants, \$9.99 / month"
GRANTS_PRODUCT_ID=$(s "$API/products/search" --get --data-urlencode "query=metadata['phoenix']:'radar-grants'" | jq_ "d['data'][0]['id'] if d['data'] else ''")
if [[ -z "$GRANTS_PRODUCT_ID" ]]; then
  GRANTS_PRODUCT_ID=$(s "$API/products" -d name="Set-Aside Radar: Grants add-on" -d "description=Every morning: the Grants.gov opportunities a small business, nonprofit, individual or tribal applicant could actually apply for, matched to a four-answer profile." \
    -d "metadata[phoenix]=radar-grants" -H "Idempotency-Key: radar-grants-product-v1" | jq_ "d['id']")
fi
GRANTS_PRICE_ID=$(s "$API/prices" --get -d product="$GRANTS_PRODUCT_ID" -d active=true -d limit=10 | jq_ "next((p['id'] for p in d['data'] if p.get('unit_amount')==999 and p.get('recurring',{}).get('interval')=='month'), '')")
if [[ -z "$GRANTS_PRICE_ID" ]]; then
  GRANTS_PRICE_ID=$(s "$API/prices" -d product="$GRANTS_PRODUCT_ID" -d unit_amount=999 -d currency=usd -d "recurring[interval]=month" \
    -d "nickname=Grants add-on monthly" -H "Idempotency-Key: radar-grants-price-999-v1" | jq_ "d['id']")
  echo "   created $GRANTS_PRICE_ID"
else
  echo "   exists  $GRANTS_PRICE_ID"
fi

echo "== webhook endpoint -> $WORKER/billing/webhook"
EP=$(s "$API/webhook_endpoints" --get -d limit=100 | jq_ "next((e for e in d['data'] if e['url']=='$WORKER/billing/webhook'), {})")
if [[ "$EP" == "{}" ]]; then
  OUT=$(s "$API/webhook_endpoints" -d url="$WORKER/billing/webhook" \
    -d "enabled_events[]=checkout.session.completed" -d "enabled_events[]=customer.subscription.created" \
    -d "enabled_events[]=customer.subscription.updated" -d "enabled_events[]=customer.subscription.deleted" \
    -d "enabled_events[]=invoice.payment_failed" -d "description=Set-Aside Radar (pbm-radar-worker)")
  WEBHOOK_SECRET=$(printf '%s' "$OUT" | jq_ "d['secret']")
  echo "   created; the signing secret is shown ONCE below"
else
  echo "   exists (signing secret is not retrievable again: roll it in the dashboard if lost)"
  WEBHOOK_SECRET=""
fi

echo
echo "== set on pbm-radar-worker (from pbm-consulting-website/radar-worker):"
echo "   printf '%s' \"\$STRIPE_SECRET_KEY\" | npx wrangler secret put STRIPE_SECRET_KEY"
[[ -n "$WEBHOOK_SECRET" ]] && echo "   printf '%s' '$WEBHOOK_SECRET' | npx wrangler secret put STRIPE_WEBHOOK_SECRET"
echo "   add to wrangler.jsonc vars:  \"STRIPE_PRICE_ID\": \"$PRICE_ID\"      (a price id is not a secret)"
echo "   add to wrangler.jsonc vars:  \"STRIPE_GRANTS_PRICE_ID\": \"$GRANTS_PRICE_ID\""
echo "   then: npx wrangler d1 execute pbm_radar_db --remote --file=migrations/2026-09-28-grants.sql"
echo "   optional: \"BILLING_ENFORCE\": \"1\" once the beta ends (canceled/past_due stops the digests)"
echo "   then: npx wrangler d1 execute pbm_radar_db --remote --file=migrations/2026-09-28-billing.sql && npx wrangler deploy"
echo "   vault (bottom of F:\\Phoenix\\Vault\\secrets\\phoenix-secrets.env): STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID (test now; swap to the live values there when live)"
echo
echo "== first real checkout (test mode): "
echo "   curl -X POST -H \"Authorization: Bearer \$PHOENIX_AUTH\" \"$WORKER/billing/checkout?subscriber=<id>\"  -> emails the link; pay with 4242 4242 4242 4242"
echo "   curl -H \"Authorization: Bearer \$PHOENIX_AUTH\" \"$WORKER/billing?subscriber=<id>\"           -> billing_status active after the webhook"
