# sector2 — Intake authority, package handler, clone pool, apps

Written 2026-09-12; corrected 2026-09-29 against the Round 2 functionality audit
(`docs/compliance/pentest/2026-09-28-round2-functionality.md`, S2CORE + CONN sections);
brought up to date 2026-09-30 with the clone-pool work since (packages-worker 3.6.0,
version backfill, pool-tidy, intake.sh 1.7.0, the road-test data plane).
Verify against current code before trusting a specific line number.

## What it is
The busiest sector: the canonical intake/clonepool pipeline, plus every Entourage app
(LifeFirst, Office, ScriptForge, the dormant lifefirst-android), plus the UnitedSys CLI
project and Frank's file-orchestration code.
- `package-handler/` — **the canonical intake pipeline** (see below). Also holds the standalone-product installers (install.sh, install.ps1, uninstall.ps1), which are not the monorepo dev-box setup.
- `package-handler/intake.sh` — intake/clone/prune CLI (version 1.7.0): hex, sidecar, T1-T4 pool, D1 custody, R2 current + per-version bytes, SHA3-512/BLAKE2b gate. Added 2026-09-29: files over ~95 MB go to R2 in 64 MB pieces through the worker's multipart routes (before that, anything over 100 MB was never uploaded); a version whose bytes are already in R2 is copied inside R2 instead of uploaded again; `intake clone` of a directory works on a machine with no local copy (pulled from R2, checked against D1); a local copy that is out-of-date against D1 is refreshed from R2 on clone (Phoenix stays the authority); directory files are pulled and verified 8 at a time (`INTAKE_PARALLEL`); a re-intaked directory keeps its unchanged files in the snapshot and manifest.
- `package-handler/worker/` — packages-worker (D1 `phoenix_dev_db` + R2 `phoenix-clonepool`): clonepool, custody, glossary, versions, deps, connections (Atlas), peer review, `/stats`. Version 3.6.0 (`index.js`), live since 2026-09-29 per `docs/plans/day-by-day-2026-09.md` (Jerry deployed it): adds the `/clonepool/<key>/mpu` routes (multipart upload for big objects) and `POST /clonepool/<key>/copy` (copy a version key inside R2, no re-upload).
- `package-handler/worker/schema-d1.sql` — the custody database's structure only, no data (50 tables, 35 indexes, exported from phoenix_dev_db 2026-09-29). Used to stand up a fresh data plane on another Cloudflare account; re-export after any live schema change so it stays the truth.
- `package-handler/backfill-versions.py` — one-time repair: finds the exact bytes of every old version that had a D1 `versions` row but no bytes in R2 (searches the local clone pools on D:, E:, F: and every blob in this repo's git history, LF and CRLF), and sends only bytes whose SHA3-512 matches D1. `python backfill-versions.py` = dry run, `--upload` = send. Needs `PHOENIX_WORKER_URL`, `PHOENIX_AUTH`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`. Run 2026-09-29: 408 version keys restored.
- `package-handler/pool-tidy.py` — keeps the local clone pool small: R2 is the home, a local copy stays only if it is pinned (e.g. a VM image a program must read from disk). `python pool-tidy.py audit` (what would go and why), `tidy [--apply]` (removes local copies only after proving their exact bytes are in R2; dry run without `--apply`), `pin|unpin <name|hex>`, `pins`. Anything it cannot prove is kept. Only reads from the worker; deletes only local files.
- `package-handler/parse-connections.js` — Atlas backfill: every CONNECTIONS.md to the D1 `connections` table (+ `connections-seed.json`).
- `package-handler/peer-review/` — peer-review schema (`schema.sql` is the truth; `PEER_REVIEW.md` is design intent).
- `apps/lifefirst/` — **retired PHP fossil** (hardcoded creds; never run its setup/deploy scripts). The live Life First backend is the `lifefirst-mcp` Cloudflare Worker (not in this repo); `meds-worker/` and `laurie/` live here.
- `apps/lifefirst-android/` — dormant Android app (`HIBERNATION_STATUS.md` present).
- `apps/office/` — tamper-evident document app. Usable end-to-end; only Module 4
  (LibreOffice format-following) is unbuilt, not on the critical path.
- `apps/scriptforge/` — sandboxed code-widget Electron app.
- `frank/` — dormant (nothing runs it; re-checked 2026-09-30). Frank3's older Python side: `frank_save.py` (Office save scheduler: picks a drive by pressure with `best_drive()`/`drive_pressure()` across `/mnt/d` to `/mnt/g`, writes to the vault CLONEPOOL), `frank_http.py` (small HTTP bridge on port 7347: `/status`, `/save`, `/catalog`), `frank_client.js` (browser-side poller for that bridge, meant for Office), `frank_helix.py` (RAM-pressure daemon, L1/L2/L3 tiers at 60/75/88 %, ZMQ). Debian-VM-shaped, no working wiring on Windows; keep or retire is Jerry's call (S2CORE-F38). The road test copies the folder to worker boxes as files, but nothing there runs it.
- `propagator/` — dormant (nothing runs it). `propagator.py` is a signal router meant to pass messages down the COM4 to COM1 chain and out to every target in `dispatch.json` (vault, sqlite, D1, Frank3, peer, Windows); `propcoms.sh` is the shell side (`propcoms.sh relay` is a stub). Same audit, same open call (S2CORE-F38).
- `ring0/` — dormant (nothing runs it). `frankenhelix.py` is the original Frank bridge: a ring0 listener with COM1-4 prefetch routing over the four physical breach_coms drives at `/media/<user>/breach_coms1-4` (needs zmq/psutil). Same open call.
- `apps/game/` — `COMPANION_VOICE.md` only: a draft of the game companion's voice and persona (2026-09-12). Notes, no code.
- `assets/` — `phoenix-logo.png`. Nothing in the code points at this copy (the dashboard and phoenix-office each use their own `assets/phoenix-logo.png`).
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
- `sector2/package-handler/intake.sh` → `sector2/package-handler/worker/index.js` (the /mpu multipart routes for big objects and /copy for version keys, both new in 3.6.0).
- `sector2/package-handler/backfill-versions.py` → `sector2/package-handler/worker/index.js` (GET /versions, then PUT /clonepool/<hex>/versions/<sha3> for each recovered version).
- `sector2/package-handler/pool-tidy.py` → `sector2/package-handler/worker/index.js` (read-only GET /clonepool/... checks before a local copy is removed).
- `sector3/worker-up/dataplane-up.sh` → `sector2/package-handler/worker/schema-d1.sql` (creates the D1 tables of a new data plane, then deploys the worker there).
- `sector3/worker-up/seed-dataplane.sh` → `sector2/package-handler/intake.sh` (seeds the new data plane through the import method).
- `sector3/worker-up/worker-bootstrap.sh` → `sector2/package-handler/intake.sh` (a worker box pulls intake.sh itself from R2, checked against D1, then uses it to pull the rest).
- `sector3/worker-up/operations-set.txt` → `sector2/frank/` (the road test ships Frank's folder, as files, to a worker box).
- `sector1/concierge/bridge.py` → `sector2/frank/frank_http.py` (hands chunks to the Frank3 HTTP bridge on port 7347; the only code caller, and the concierge bridge itself is not run on this project).
- `dashboard/scriptforge-launcher.js` → `sector2/apps/scriptforge/index.html`.
- `dashboard/office-launcher.js` → `sector2/apps/office/index.html` (+ `sector2/apps/office/preload.js`; its IPC channels are cross-checked against office-launcher.js, the Office index.html and `dashboard/button-generator.js`).
- `apps/office/notify-worker/wrangler.jsonc` comment → points at
  `sector2/package-handler/rotate-phoenix-auth.sh` for secret rotation.
- `install.ps1` (repo root) clones the standalone `Phoenix-Package_handler` GitHub repo into
  `$INSTALL_ROOT/package-handler`, a sibling of the OS repo (plain clone, no git subtree) —
  this is the 3-way package-handler drift.

## Known issues (verified, not guessed)
- `sector2/frank/frank_save.py`'s tiering logic (`best_drive()` etc.) is unused: nothing calls it.
  `intake.sh` always places new intakes in T1; its own T1→T4 rotation only runs on a manual
  `intake prune` (nothing schedules it — S2CORE-F24, Jerry's call).
- Local vN labels and D1 `versions` labels are independent counters (S2CORE-F23), and
  `hex_id = to_hex(basename)` collides for same-named files (S2CORE-F25) — both open.
- Per-version R2 bytes: `intake.sh` uploads them from 2026-09-29 on, and the 408 older
  `versions` rows got their bytes the same night through `backfill-versions.py` (per
  `docs/plans/day-by-day-2026-09.md`). Not re-checked live here.
- The systemd units for the dormant code point at files that do not exist:
  `sector3/services/phoenix-frank-helix.service` runs `sector1/frank_helix.py`,
  `phoenix-frankenhelix.service` runs `sector1/frankenhelix.py`, `phoenix-propagator.service`
  runs `sector2/propagator.py`, all under `/home/jwl247/projects/phoenix`. `install-units.sh`
  refuses to install them (S34OPS-F04).
- `intake.sh`'s header comment still says `Version: 1.5.0`; the real `VERSION` is 1.7.0.
- `apps/lifefirst-android/` is dormant (`HIBERNATION_STATUS.md`), has a typo'd
  `TransformViewModek.kt` and a stray `.gitmore` file — stale, not actively maintained.
- `apps/lifefirst/lifefirst_setup.sh` and `deploy_lifefirst.sh` are deprecated and still on
  disk — don't use them (nor the rest of the retired PHP tree).
- `apps/lifefirst/meds-worker` is still not deployed; its 2026-09-14 deadline was voided
  2026-09-21.
- `package-handler/.github/workflows/deploy.yml` only works at the standalone repo's root;
  GitHub never evaluates it inside this monorepo.
