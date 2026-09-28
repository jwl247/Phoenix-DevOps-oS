# Set-Aside Radar — `pbm-radar-worker`

Public page + application form: https://pbmconsultingservice.com/radar (`../radar.html`, `../radar.js`). $9.99/month (Jerry, 2026-09-27), free during the beta; nobody is charged without being asked first. Every application is reviewed by hand.

Every morning (6 AM Central, cron `0 11 * * *`) Radar pulls the federal opportunities
posted the previous day from the **SAM.gov Opportunities API v2**, keeps only the
**set-asides**, matches them to each subscriber by **NAICS + certification + state +
notice type**, and emails a digest meant to be read in ten seconds.
It's Laurie's product, and PBM is customer zero.

- Live: `https://pbm-radar-worker.phoenix-jwl.workers.dev`
- D1: `pbm_radar_db` (its own database, shared with no other worker)

## How it works
- **Budget.** A free non-federal SAM.gov key allows 10 requests/day, and one request
  returns up to 1,000 notices. A day's postings take roughly 2–5 requests. Radar caps
  itself at 8 per Chicago day, counted across every run, so a manual re-run can't use up
  the key's allowance. Once PBM's SAM entity registration exists, the limit rises to 1,000/day.
- **Matching.** A bid matches only if all of these hold:
  - its NAICS is in the subscriber's list (a prefix like `2381` covers all of 2381xx);
  - its set-aside code is one the subscriber's certs qualify for (map below);
  - its state is in the subscriber's list, or the list is empty (nationwide), or the bid gives no place;
  - its notice type is wanted (default: solicitation, combined, presolicitation, sources sought).
  Unknown notice-type wording is let through, so a SAM wording change can't silently hide bids.
- **Cert → set-aside codes:**
  - small → SBA, SBP
  - 8a → 8A, 8AN
  - hubzone → HZC, HZS
  - wosb → WOSB, WOSBSS
  - edwosb → EDWOSB, EDWOSBSS, WOSB, WOSBSS
  - sdvosb → SDVOSBC, SDVOSBS
  - vosb → VSA, VSS
  - iee / isbee / buyindian
- **Planning mode.** This is for firms that aren't certified yet, which is PBM today.
  Radar matches against the certs the firm is *pursuing* and marks each bid
  "eligible once certified".
- **Never twice.** `sent_matches` remembers every bid a subscriber has already been sent.
- **Quiet days.** On a day with no matches, no email goes out. On Monday, a short weekly
  check-in goes out instead, so silence never looks like breakage.
- **Honest record.** Every run writes a `runs` row: requests used, notices seen,
  set-asides kept, matches per subscriber, and any error. The digest footer states the same numbers.
- **Real SAM quirks handled (found live 2026-09-27):** bids already past their deadline are dropped; `"0"` city placeholders are ignored; when `placeOfPerformance.state` is empty the state is read from the street-address text ("…Yuma, Arizona" → AZ).
- The SAM key is redacted out of every error, log and response (tested).

## Routes
| Route | Auth | What |
|---|---|---|
| `GET /health` | none | db / sam_key / transport / admin_auth / last run (no secret values) |
| `POST /apply` | Turnstile (`radar_apply`) | public application from `pbmconsultingservice.com/radar`: validates, emails a 6-digit code (15 min, 5 tries, hash only stored) |
| `POST /apply/verify` | code | confirms email -> status `review`, emails reviewers (`ADMIN_NOTIFY_EMAIL`) a one-time review link, tells the applicant it's in |
| `GET /review/:token` | token | shows the application with Approve / Decline (GET never acts) |
| `POST /review/:token` | token | `action=approve` -> subscriber + welcome email; `action=reject` -> declined, applicant not emailed. Link dies after use |
| `GET /applications?status=` | Bearer | list (no hashes/tokens) |
| `POST /applications/approve?id=` | Bearer | approve, optional JSON overrides `{naics,states,certs,mode}` (needed when they only described their work) |
| `POST /applications/reject?id=` | Bearer | decline |
| `GET /unsub/:token` | token | confirm page (a GET alone never acts; mail scanners follow links) |
| `POST /unsub/:token` | token | unsubscribe (RFC 8058 one-click lands here) |
| `POST /billing/checkout?subscriber=` | Bearer | **asks first, never charges**: creates/reuses the Stripe customer, a subscription Checkout Session for `STRIPE_PRICE_ID` ($9.99/mo), emails the subscriber the link (cards go to Stripe, never here). 409 if unsubscribed or already active; 503 without Stripe keys |
| `GET /billing?subscriber=` | Bearer | billing_status, Stripe ids, last 10 webhook events |
| `POST /billing/webhook` | Stripe signature | `Stripe-Signature` (t + v1 HMAC-SHA256 over `t.body`, 5-min tolerance, constant-time) is the auth; each event id acted on once (`billing_events`); `checkout.session.completed` → active, `customer.subscription.*` → status map, `invoice.payment_failed` → past_due. With `BILLING_ENFORCE=1` (off during the beta) canceled/past_due also stops the digests (`active=0`) |
| `POST /grants/run?dry=1&fetch=0&since=` | Bearer | **Grants add-on** run: Grants.gov `search2` (public, no key) for everything posted since `since` (default yesterday), one `fetchOpportunity` per new opportunity (applicant types, categories, ceiling, close date), match per subscriber with `grants=1`, never twice (`grant_matches`), `runs` row with `kind='grants'`. Capped at 250 calls per run |
| `GET /grants/preview?subscriber=&since=` | Bearer | matches from stored grants, no calls |
| `GET /whoami` | Bearer `PHOENIX_AUTH` | rotation check |
| `POST /subscribers` | Bearer | create/update by email: `{email,name,naics[],certs[],states[],ptypes[],mode}` |
| `GET /subscribers` | Bearer | list |
| `GET /preview?subscriber=&date=YYYY-MM-DD` | Bearer | matches from stored bids (costs no SAM request) |
| `POST /run?dry=1&fetch=0&date=` | Bearer | manual run. `dry=1` builds the email but doesn't send; `fetch=0` reuses stored bids |
| `GET /runs` | Bearer | last 30 runs |

## Grants add-on (2026-09-28)

Paid add-on to Radar ($9.99/month extra, free during the beta; `STRIPE_GRANTS_PRICE_ID` as a second Checkout line item with `?addon=grants`, and the flag then follows the Stripe subscription items). The subscriber's **grant profile is a four-answer survey** (on the public form under "Grants add-on", or via `POST /subscribers`):

| Field | Meaning | Match rule |
|---|---|---|
| `grant_eligibility` | who would apply — Grants.gov applicant-type codes: `23` small business, `22` other for-profit, `21` individual, `12`/`13` nonprofit, `07`/`11` tribal, `99` unrestricted | overlap with the grant's applicant types; a grant with no types listed passes |
| `grant_categories` | what for — Grants.gov funding categories (`BC`, `CD`, `ELT`, `EN`, `ENV`, `HO`, `ST`, `T`, `RD`, `AG`, `DPR`, `ED`, …) | overlap; empty = all; a grant with no category passes |
| `grant_keywords` | a few words about the work (up to 20) | any keyword in the title; empty = all |
| `grant_min_award` | about how much they need (whole dollars) | grants whose maximum award is below it are dropped; unknown ceilings pass |

Runs in the same daily cron, after the SAM pull. Every digest says "a grant is an application, not a bid". Field names follow api.grants.gov's public documentation; the first live run from a box with egress confirms them (the build container had none) — check the `runs` row's `error` after the first cron. Existing database: `migrations/2026-09-28-grants.sql` once.

## Secrets
- `SAM_API_KEY`: sam.gov → Account Details → request public API key. **Expires every 90 days.**
- `RESEND_API_KEY`
- `RESEND_FROM`: `Set-Aside Radar <radar@pbmconsultingservice.com>`
- `TURNSTILE_SECRET`: application-form bot check, widget `pbm-radar-application` (sitekey `0x4AAAAAAFFZlAsR3JQ08oA0`). Vault copy: `RADAR_TURNSTILE_SECRET`. `TURNSTILE_HOSTNAMES` var = `pbmconsultingservice.com` (no localhost in production). Fails closed.
- `ADMIN_NOTIFY_EMAIL`: comma list of reviewers who get "new application" notices (a secret so emails stay out of the public repo).
- `PHOENIX_AUTH`: a leg in `sector2/package-handler/rotate-phoenix-auth.sh`. Never hand-set it.
- `STRIPE_SECRET_KEY` (secret), `STRIPE_WEBHOOK_SECRET` (secret), `STRIPE_PRICE_ID` (var, not a secret), `BILLING_ENFORCE` (var, `1` after the beta). One-time setup, test or live: `tools/stripe/setup-radar.sh` (creates product + $9.99/month price + webhook endpoint, prints the exact `wrangler secret put` lines). Existing database: `npx wrangler d1 execute pbm_radar_db --remote --file=migrations/2026-09-28-billing.sql` once. Values live in the vault (`phoenix-secrets.env`) like every other worker secret.

## Run / test / deploy
```bash
npm test                                  # 50 tests, real SQLite via node:sqlite, SAM + Grants.gov + Resend + Stripe faked
npx wrangler deploy
npx wrangler d1 execute pbm_radar_db --remote --file=schema.sql   # schema (idempotent)
curl -X POST -H "Authorization: Bearer $PHOENIX_AUTH" "https://pbm-radar-worker.phoenix-jwl.workers.dev/run?dry=1"
```

## Not in v1 (schema ready)
- **Self-serve profile editing** (Jerry 2026-09-27: "it needs an add or remove code"): a subscriber adds or removes NAICS codes (and states/certs) themselves, from a link in the digest. It would reuse the unsub-token pattern and a small form.
- **Award watch** (2026-09-27, McConnell MACC): follow a bid and get its award notice, so you can pitch the winners for sub work.
- Paid tiers ($29 / $99).
- Full bid descriptions (each one costs a SAM request).
