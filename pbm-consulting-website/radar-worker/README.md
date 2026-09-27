# Set-Aside Radar — `pbm-radar-worker`

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
| `GET /unsub/:token` | token | confirm page (a GET alone never acts; mail scanners follow links) |
| `POST /unsub/:token` | token | unsubscribe (RFC 8058 one-click lands here) |
| `GET /whoami` | Bearer `PHOENIX_AUTH` | rotation check |
| `POST /subscribers` | Bearer | create/update by email: `{email,name,naics[],certs[],states[],ptypes[],mode}` |
| `GET /subscribers` | Bearer | list |
| `GET /preview?subscriber=&date=YYYY-MM-DD` | Bearer | matches from stored bids (costs no SAM request) |
| `POST /run?dry=1&fetch=0&date=` | Bearer | manual run. `dry=1` builds the email but doesn't send; `fetch=0` reuses stored bids |
| `GET /runs` | Bearer | last 30 runs |

## Secrets
- `SAM_API_KEY`: sam.gov → Account Details → request public API key. **Expires every 90 days.**
- `RESEND_API_KEY`
- `RESEND_FROM`: `Set-Aside Radar <radar@pbmconsultingservice.com>`
- `PHOENIX_AUTH`: a leg in `sector2/package-handler/rotate-phoenix-auth.sh`. Never hand-set it.

## Run / test / deploy
```bash
npm test                                  # 25 tests, real SQLite via node:sqlite, SAM + Resend faked
npx wrangler deploy
npx wrangler d1 execute pbm_radar_db --remote --file=schema.sql   # schema (idempotent)
curl -X POST -H "Authorization: Bearer $PHOENIX_AUTH" "https://pbm-radar-worker.phoenix-jwl.workers.dev/run?dry=1"
```

## Not in v1 (schema ready)
- Public signup page on pbmconsultingservice.com (would reuse pbm-leads' Turnstile + email code).
- Paid tiers ($29 / $99).
- Full bid descriptions (each one costs a SAM request).
