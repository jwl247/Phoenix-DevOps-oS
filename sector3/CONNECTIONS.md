# sector3 — Comms/networking, systemd services

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
- `quadengine/quadengine.py` — the quadralingual comms engine.
- `romeo_juliet/` — `romeo.py` (ingress), `juliet.py`/`dbl_juliet.py` (egress).
- `translator/translator.sh` — fires on OUTPUT only, never on intake (Critical Rule #2 in
  root CLAUDE.md — do not call this from an intake path).
- `services/` — 17 systemd `.service`/`.target` files + `install-units.sh`, plus the
  Windows/Ubuntu dashboard deploy scripts (`deploy-dashboard.sh`, `push-dashboard.sh/.ps1`,
  `install-dashboard-windows.ps1`, `scout-ubuntu.sh`).
- `workers/packages-worker/` — **a stale, dead duplicate**, see Known issues.

## Dependencies
`sector3/workers/packages-worker/wrangler.jsonc` — D1 `DEV_DB`→`phoenix_dev_db`,
`CATALOG_DB`→`phoenix-catalog` (a DB not referenced anywhere else in the repo), R2
`CLONEPOOL_BUCKET`→`phoenix-clonepool`. This file is dated Aug 20-22 and differs in size
from the real live worker — it is NOT the one actually deployed.

## Commands / entry points
- `sector3/services/install-units.sh` — installs all the systemd units.
- `sector3/services/install-dashboard-windows.ps1` — Windows dashboard autostart (called
  from repo-root `install.ps1`).
- `sector3/services/deploy-dashboard.sh` — invoked remotely by `deploy/deploy.sh`.
- `sector3/translator/translator.sh` — promoted into systemd via `deploy/deploy.sh`.

## Connects to / connected from
- `deploy/deploy.sh` rsyncs `sector3/services/` to a remote Ubuntu box, then runs
  `deploy-dashboard.sh` remotely, and also manages a remote copy of `dashboard/` — i.e.
  sector3's deploy scripting directly reaches into `dashboard/`.
- `install.ps1` (repo root) → `sector3/services/install-dashboard-windows.ps1`.
- `dashboard/main.js` maps sector slots `'1'/'2'/'3'` → `sector1/2/3` and also references
  `SECTOR4` (see Known issues — casing bug).

## Known issues (verified, not guessed)
- **`sector3/workers/packages-worker/` is a stale/orphaned duplicate.** The live worker is
  `sector2/package-handler/worker/index.js`. A docs file
  (`docs/PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md`) still points at this dead path —
  known-stale, don't trust that doc, trust this file and its sibling in `sector2/`.
- **`dashboard/main.js` (~line 374) references `'SECTOR4'` uppercase**, but the real
  directory on disk is lowercase `sector4/`. Works today because Windows NTFS is
  case-insensitive by default — would break on a case-sensitive filesystem (the target
  Ubuntu deploy box). Not yet fixed as of this writing.
- `sector3/services/phoenix-unoserver.service` is dormant, waiting on Office Module 4
  (not yet built) — this is intentional, not a bug.
