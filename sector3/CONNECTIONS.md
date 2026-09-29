# sector3 — Comms/networking, systemd services, Phoenix Mesh

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F23/F27/F34/F35/F36, CONN-F01/F02/F19).
Verify against current code before trusting a specific line number.

## What it is
- `quadengine/quadengine.py` — the quadralingual comms engine.
- `romeo_juliet/` — `romeo.py` (ingress), `juliet.py`/`dbl_juliet.py` (egress); loopback-bound by default, need pyzmq.
- `translator/translator.sh` — 9 package backends; fires on OUTPUT only, never on intake (Critical Rule #2 in root CLAUDE.md — do not call this from an intake path).
- `services/` — 19 systemd `.service`/`.target` files, `install-units.sh` (explicit allow-list), and the dashboard deploy scripts (`deploy-dashboard.sh`, `push-dashboard.ps1`/`.sh`, `install-dashboard-windows.ps1`, `scout-ubuntu.sh`).
- `phoenix-net/` — Phoenix Mesh: switchboard worker, per-machine agent, admin tool (own CONNECTIONS.md).
- `workers/packages-worker/` — a stale duplicate of the live worker, see Known issues.

## Dependencies
- `sector3/phoenix-net/mesh-worker/wrangler.jsonc` — own D1 `phoenix_mesh`, own secret `MESH_ADMIN`.
- `sector3/workers/packages-worker/wrangler.jsonc` — stale: D1 `DEV_DB`→`phoenix_dev_db`,
  `CATALOG_DB`→`phoenix-catalog` (deleted 2026-09-25), R2 `CLONEPOOL_BUCKET`. Not what is deployed.
- romeo/juliet/quadengine need `pyzmq` (not installed on the Windows box; no requirements file here).

## Commands / entry points
- `sudo sector3/services/install-units.sh <unit> …` — installs only allow-listed units
  (`helix.service`, `phoenix-paging.service`, `phoenix-helix-kernel.service`); no args prints usage.
- `sector3/services/push-dashboard.ps1 -UbuntuHost … -UbuntuUser …` (Windows, PS7) — scouts the
  box (`scout-ubuntu.sh`), `scp`s `sector3/services/` + `dashboard/`, runs `deploy-dashboard.sh`
  there, installs Claude Code. `push-dashboard.sh <host> [user]` is the bash twin.
- `sector3/services/install-dashboard-windows.ps1` — Windows dashboard autostart (called from repo-root `install.ps1`).
- `sector3/translator/translator.sh <verb> [pkg]` — promoted to `/etc/systemd/system/translator.sh` by `deploy/deploy.sh`.

## Connects to / connected from
- `sector3/services/push-dashboard.ps1` → `sector3/services/scout-ubuntu.sh` → `sector3/services/deploy-dashboard.sh` (remote) → `dashboard/`.
- `sector3/services/push-dashboard.sh` → `sector3/services/deploy-dashboard.sh` (remote).
- `deploy/deploy.sh` → `sector3/translator/translator.sh` (local copy into systemd dirs).
- `sector3/romeo_juliet/juliet.py` → `sector3/translator/translator.sh` (output translation; promoted copy first, repo copy as fallback).
- `install.ps1` → `sector3/services/install-dashboard-windows.ps1`.
- `sector3/services/phoenix-paging.service` → `sector4/paging.py`; `sector3/services/helix.service` → `sector1/kernels/helix_boot.sh`.
- `portal/server.py` → `sector3/phoenix-net/mesh-worker/index.js`.
- `dashboard/main.js` maps sector slots `'1'/'2'/'3'` → `sector1/2/3` and `'4'` → `sector4`.

## Known issues (verified, not guessed)
- **`sector3/workers/packages-worker/` is a stale duplicate.** The live worker is
  `sector2/package-handler/worker/index.js`. It shares the name `packages-worker` and has no
  auth on its `/custody`, `/clonepool`, `/packages` GETs; its `wrangler.jsonc` `main` points at
  a nonexistent file so a deploy fails loudly. Deleting the folder is Jerry's call (S34OPS-F44).
- 9 units (`phoenix-auto-config`, `-frankenhelix`, `-frank-helix`, `-intent-parser`,
  `-propagator`, `-mega-security`, `-unoserver`, `-doc-worker`, `-scheduler`) point at
  `/home/jwl247/projects/phoenix` paths that are missing or moved (S34OPS-F04);
  `install-units.sh` refuses them. `frank3-slot-a/b.service` (kernel modules) need Jerry (F05).
- `phoenix-unoserver.service` is waiting on Office Module 4 on purpose.
- `deploy-dashboard.sh` still installs Node with an unpinned `curl … nodesource | sudo bash`
  (S34OPS-F35, noted in place).
