# sector2 — Intake authority, package handler, clone pool, apps

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
The busiest sector: the canonical intake/clonepool pipeline, plus every Entourage app
(LifeFirst, Office, ScriptForge, the dormant lifefirst-android), plus the UnitedSys CLI
project and Frank's file-orchestration code.
- `package-handler/` — **the canonical intake pipeline** (see below).
- `apps/lifefirst/` — Laurie's Life First app (PHP modules + `meds-worker` Cloudflare
  Worker + `laurie/` front door). Deployed and live at `lifefirst.authenticcoder.com`.
- `apps/lifefirst-android/` — dormant Android app (`HIBERNATION_STATUS.md` present).
- `apps/office/` — tamper-evident document app. Usable end-to-end; only Module 4
  (LibreOffice format-following) is unbuilt, not on the critical path.
- `apps/scriptforge/` — sandboxed code-widget Electron app.
- `frank/` — `frank_save.py` has real drive-pressure tiering logic (`best_drive()`,
  `drive_pressure()`) that **nothing calls**. `frank_helix.py`, `frank_http.py`,
  `frank_client.js` — not deeply audited this pass.
- `propagator/`, `ring0/` — `propagator.py`/`dispatch.json`/`propcoms.sh`,
  `frankenhelix.py` — not deeply audited this pass.
- `unitedsys/` — a separate CLI project (`bin/us`, `core/*.py`, `db/schema.sql`,
  `manifests/example.toml`) — its relationship to `scripts/usys.ps1` (same name space,
  different implementation) is unconfirmed; don't assume one supersedes the other.

## Dependencies
- `package-handler/worker/wrangler.jsonc` — D1 `PHOENIX_DB`→`phoenix_dev_db`. Comment:
  never `wrangler secret put PHOENIX_AUTH` directly here — use `rotate-phoenix-auth.sh`.
- `package-handler/r2-worker/wrangler.jsonc` — R2 `CLONEPOOL_BUCKET`→`phoenix-clonepool`.
- `apps/lifefirst/meds-worker/wrangler.jsonc` — D1 `DB`→`lifefirst-db`, cron `*/5 * * * *`.
  Secrets needed: `PHOENIX_AUTH`, `PUSHOVER_*`, `RESEND_API_KEY`, email/SMS contacts.
  **Code-complete, tested (20/20), not deployed.**
- `apps/office/notify-worker/wrangler.jsonc` — D1 `PHOENIX_DB`, cron `* * * * *`. Deployed
  live 2026-09-09, but `RESEND_API_KEY` unset → `/health` reports `transport: NONE`.
- `apps/lifefirst-android/functions/requirements.txt` — `firebase_functions~=0.1.0`.
- `unitedsys/db/schema.sql`, `unitedsys/manifests/example.toml` — UnitedSys's own schema/format.

## Commands / entry points
- `sector2/package-handler/intake.sh <cmd>` — the canonical intake pipeline (R2 upload,
  SHA3-512+BLAKE2b integrity, QR gen, sensitive-file flagging). Reached via `usys clone`.
- `sector2/package-handler/rotate-phoenix-auth.sh` — rotates `PHOENIX_AUTH` across every
  worker leg, verifying each before moving on.
- `sector2/apps/lifefirst/install.sh` — one idempotent LifeFirst installer (Debian target).
- `wrangler deploy` inside any `apps/*/notify-worker` or `meds-worker` — deploys that worker.
- `sector2/unitedsys/bin/us` / `bin/us.ps1` — UnitedSys CLI entry point.

## Connects to / connected from
- `bin/clone` → `tools/clone.sh` → `sector2/package-handler/intake.sh` (confirmed).
- `scripts/usys.ps1` line ~160 → `sector2/package-handler/intake.sh` (canonical clone path).
- `dashboard/scriptforge-launcher.js` → `sector2/apps/scriptforge/index.html`.
- `dashboard/office-launcher.js` → `sector2/apps/office/index.html` (+ `preload.js` IPC
  channels cross-checked against `office-launcher.js`/`index.html`/`button-generator.js`).
- `apps/office/notify-worker/wrangler.jsonc` comment → points at
  `sector2/package-handler/rotate-phoenix-auth.sh` for secret rotation.
- `install.ps1` (repo root) clones the standalone `Phoenix-Package_handler` GitHub repo
  into `sector2/package-handler` as a git subtree (see peripheral-folder connections for
  the 3-way package-handler drift).

## Known issues (verified, not guessed)
- `sector2/frank/frank_save.py`'s tiering logic (`best_drive()` etc.) is fully orphaned —
  `intake.sh` hardcodes `"tier": 1` and never calls it.
- `apps/lifefirst-android/` is dormant (`HIBERNATION_STATUS.md`), has a typo'd
  `TransformViewModek.kt` and a stray `.gitmore` file — stale, not actively maintained.
- `apps/lifefirst/lifefirst_setup.sh` and `deploy_lifefirst.sh` are deprecated, superseded
  by `apps/lifefirst/install.sh` (2026-09-04) — still present on disk, don't use them.
- `apps/office/notify-worker`: `handleNotify` returns HTTP 502 on send failure even though
  the D1 row was written — a naive retry-on-502 client could double-insert.
- `apps/lifefirst/meds-worker` has a hard external deadline (2026-09-14 per CLAUDE.md) and
  is not deployed as of this writing — check current state before assuming it's still open.
