# sector2 — Intake authority, package handler, clone pool, apps

Written 2026-09-12; corrected 2026-09-29 against the Round 2 functionality audit
(`docs/compliance/pentest/2026-09-28-round2-functionality.md`, S2CORE + CONN sections).
Verify against current code before trusting a specific line number.

## What it is
The busiest sector: the canonical intake/clonepool pipeline, plus every Entourage app
(LifeFirst, Office, ScriptForge, the dormant lifefirst-android), plus the UnitedSys CLI
project and Frank's file-orchestration code.
- `package-handler/` — **the canonical intake pipeline** (see below). Also holds the standalone-product installers (install.sh, install.ps1, uninstall.ps1), which are not the monorepo dev-box setup.
- `package-handler/intake.sh` — intake/clone/prune CLI: hex, sidecar, T1-T4 pool, D1 custody, R2 current + per-version bytes, SHA3-512/BLAKE2b gate.
- `package-handler/worker/` — packages-worker (D1 `phoenix_dev_db` + R2 `phoenix-clonepool`): clonepool, custody, glossary, versions, deps, connections (Atlas), peer review, `/stats`.
- `package-handler/parse-connections.js` — Atlas backfill: every CONNECTIONS.md to the D1 `connections` table (+ `connections-seed.json`).
- `package-handler/peer-review/` — peer-review schema (`schema.sql` is the truth; `PEER_REVIEW.md` is design intent).
- `apps/lifefirst/` — **retired PHP fossil** (hardcoded creds; never run its setup/deploy scripts). The live Life First backend is the `lifefirst-mcp` Cloudflare Worker (not in this repo); `meds-worker/` and `laurie/` live here.
- `apps/lifefirst-android/` — dormant Android app (`HIBERNATION_STATUS.md` present).
- `apps/office/` — tamper-evident document app. Usable end-to-end; only Module 4
  (LibreOffice format-following) is unbuilt, not on the critical path.
- `apps/scriptforge/` — sandboxed code-widget Electron app.
- `frank/` — dormant: `frank_save.py` drive-pressure tiering (`best_drive()`, `drive_pressure()`) that nothing calls, plus `frank_helix.py`, `frank_http.py`, `frank_client.js`. Audited 2026-09-28: Debian-VM-shaped, no working wiring on Windows (keep or retire is Jerry's call, S2CORE-F38).
- `propagator/` — dormant: `propagator.py`/`dispatch.json`/`propcoms.sh` (`propcoms.sh relay` is a stub); same audit, same open call (S2CORE-F38).
- `ring0/` — dormant: `frankenhelix.py` (COM router self-loop, needs zmq/psutil); same open call.
- `unitedsys/` — a separate CLI project (`bin/us`, `bin/us.ps1`, `core/*.py`, `db/schema.sql`, `manifests/*.toml`). Confirmed 2026-09-28: a different implementation from `scripts/usys.ps1` (different DB, different verbs); neither supersedes the other.

## Dependencies
- `package-handler/worker/wrangler.jsonc` — D1 `PHOENIX_DB`→`phoenix_dev_db` and R2
  `CLONEPOOL_BUCKET`→`phoenix-clonepool`. Never `wrangler secret put PHOENIX_AUTH`
  directly here — use `rotate-phoenix-auth.sh`.
- `package-handler/r2-worker/` — the retired `phoenix-clonepool-r2` worker (retired
  2026-09-21, deleted from Cloudflare 2026-09-25). Its `wrangler.jsonc` is still intact, so a
  `wrangler deploy` there would recreate it against the real bucket — don't; removal is
  Jerry's call (S2CORE-F40).
- `apps/lifefirst/meds-worker/wrangler.jsonc` — D1 `DB`→`lifefirst-db`, cron `*/5 * * * *`.
  Secrets needed: `PHOENIX_AUTH`, `PUSHOVER_*`, `RESEND_API_KEY`, email/SMS contacts.
  **Code-complete, tested (20/20), not deployed.**
- `apps/office/notify-worker/wrangler.jsonc` — D1 `PHOENIX_DB`, cron `* * * * *`. Deployed
  live 2026-09-09; `RESEND_API_KEY` has since been set (`/health` → `transport: resend`, 2026-09-28).
- `apps/lifefirst-android/functions/requirements.txt` — `firebase_functions~=0.1.0`.
- `unitedsys/db/schema.sql`, `unitedsys/manifests/example.toml` — UnitedSys's own schema/format.
- `openssl` (SHA3-512/BLAKE2b) is required by `intake.sh`; `sqlite3` CLI and `jq` are optional
  (without `sqlite3` the local custody ledger is a no-op).

## Commands / entry points
- `sector2/package-handler/intake.sh <cmd>` — the canonical intake pipeline (R2 upload,
  SHA3-512+BLAKE2b integrity, QR gen, sensitive-file flagging). Reached via `usys clone`,
  `tools/clone.sh` and `scripts/hsf-intake.sh`. `INTAKE_YES=1` for unattended runs.
- `sector2/package-handler/rotate-phoenix-auth.sh` — rotates `PHOENIX_AUTH` across every
  worker leg, verifying each before moving on.
- `node sector2/package-handler/parse-connections.js [--dry-run]` — refresh the Atlas.
- `wrangler deploy` inside any `apps/*/notify-worker` or `meds-worker` — deploys that worker.
- `sector2/unitedsys/bin/us` (zsh) / `bin/us.ps1` (Windows) — UnitedSys CLI entry points.
- Do **not** run `apps/lifefirst/install.sh`, `lifefirst_setup.sh` or `deploy_lifefirst.sh`
  (retired PHP tree, see above).

## Connects to / connected from
- `bin/clone` → `tools/clone.sh` → `sector2/package-handler/intake.sh` (confirmed).
- `scripts/usys.ps1` (`Get-UsysCloneIntakeSh`) → `sector2/package-handler/intake.sh` (canonical clone path).
- `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh` (directly, not via usys).
- `dashboard/office-launcher.js` → `sector2/package-handler/intake.sh` (Office "save" = intake).
- `sector2/package-handler/intake.sh` → `sector3/translator/translator.sh` (`deps` verb, backend intakes).
- `dashboard/main.js` (`get-phoenix-stats`) → `sector2/package-handler/worker` `GET /stats`.
- `sector2/package-handler/parse-connections.js` → `sector2/package-handler/worker` (`POST /connections`, `/connections/reconcile`).
- `dashboard/scriptforge-launcher.js` → `sector2/apps/scriptforge/index.html`.
- `dashboard/office-launcher.js` → `sector2/apps/office/index.html` (+ `preload.js` IPC
  channels cross-checked against `office-launcher.js`/`index.html`/`dashboard/button-generator.js`).
- `apps/office/notify-worker/wrangler.jsonc` comment → points at
  `sector2/package-handler/rotate-phoenix-auth.sh` for secret rotation.
- `install.ps1` (repo root) clones the standalone `Phoenix-Package_handler` GitHub repo into
  `$INSTALL_ROOT/package-handler`, a sibling of the OS repo (plain clone, no git subtree) —
  this is the 3-way package-handler drift.

## Known issues (verified, not guessed)
- `sector2/frank/frank_save.py`'s tiering logic (`best_drive()` etc.) is fully orphaned.
  `intake.sh` always places new intakes in T1; its own T1→T4 rotation only runs on a manual
  `intake prune` (nothing schedules it — S2CORE-F24, Jerry's call).
- Local vN labels and D1 `versions` labels are independent counters (S2CORE-F23), and
  `hex_id = to_hex(basename)` collides for same-named files (S2CORE-F25) — both open.
- Per-version R2 bytes: `intake.sh` uploads them from 2026-09-29 on; the 408 older `versions`
  rows have no bytes in R2 (backfill needs Jerry).
- `apps/lifefirst-android/` is dormant (`HIBERNATION_STATUS.md`), has a typo'd
  `TransformViewModek.kt` and a stray `.gitmore` file — stale, not actively maintained.
- `apps/lifefirst/lifefirst_setup.sh` and `deploy_lifefirst.sh` are deprecated and still on
  disk — don't use them (nor the rest of the retired PHP tree).
- `apps/lifefirst/meds-worker` is still not deployed; its 2026-09-14 deadline was voided
  2026-09-21.
- `package-handler/.github/workflows/deploy.yml` only works at the standalone repo's root;
  GitHub never evaluates it inside this monorepo.
