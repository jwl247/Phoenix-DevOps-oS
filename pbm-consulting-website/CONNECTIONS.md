# pbm-consulting-website — PBM's public site, lead form and Set-Aside Radar

Written 2026-09-30 (CONN-F01) from the code in this folder. Verify against current code
before trusting a specific line number.

## What it is
Three separate Cloudflare deploys from one folder, for PBM Consulting Service (Laurie's
company). `.assetsignore` keeps both worker folders out of the public site.
- `index.html` / `story.html` / `privacy.html` / `terms.html` / `styles.css` / `app.js` — the public site at pbmconsultingservice.com (Workers static assets, `wrangler.jsonc`, name `pbm-consulting-website`).
- `radar.html` / `radar.js` — the Set-Aside Radar sign-up page (pbmconsultingservice.com/radar): application form with a Turnstile bot check and an email code.
- `worker/` — `pbm-leads-worker`: the site's contact/lead form (Turnstile, email code, D1).
- `radar-worker/` — `pbm-radar-worker`, Set-Aside Radar: every morning (cron `0 11 * * *`) pulls new SAM.gov set-aside contracts, matches them to each subscriber's work codes, certifications and states, and emails a short digest. Applications are approved by hand (Laurie/Jerry get a one-click review link). Billing: $9.99/month through a Stripe Payment Link + signed webhook; nobody is charged without being asked first (`POST /subscribers/ask-to-pay`). D1 `pbm_radar_db`. Routes and secrets in `radar-worker/README.md`.
- `radar-worker/stripe-setup.sh` — makes the Stripe product, price, payment link and webhook and deploys (`test` or `live`; Git Bash, key read from the vault, never printed).

## Dependencies
Cloudflare Workers + D1, Resend (email), Turnstile, SAM.gov public API key (expires every
90 days), Stripe. Node for the tests.

## Commands / entry points
- `cd pbm-consulting-website && npx wrangler deploy` (site).
- `cd pbm-consulting-website/radar-worker && npm test`, `npx wrangler deploy`.
- `bash pbm-consulting-website/radar-worker/stripe-setup.sh test|live`.

## Connects to / connected from
- `pbm-consulting-website/radar.js` → `pbm-consulting-website/radar-worker/index.js` (the sign-up form posts `/apply` and `/apply/verify`).
- `pbm-consulting-website/app.js` → `pbm-consulting-website/worker/index.js` (the lead form).
- `pbm-consulting-website/radar-worker/index.js` → `sector2/package-handler/rotate-phoenix-auth.sh` (its admin key is one leg of the PHOENIX_AUTH rotation).

## Known issues (verified, not guessed)
- Radar charging is in Stripe TEST mode until `stripe-setup.sh live` is run with
  `STRIPE_SECRET_KEY_LIVE` in the vault (not there as of 2026-09-30 night).
- A Grants add-on (Grants.gov) was built on branch `claude/zealous-lamport-63hnfd`
  (commit `7271aca`) against a different billing design; parked, not on main (Jerry,
  2026-09-30).
