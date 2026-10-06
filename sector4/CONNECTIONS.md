# sector4 — vault intake, paging brain, PCS

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F22/F26/F30, CONN-F07/F08); re-checked
2026-09-30 against the code since (paging alongside the Helix ingress/egress pair). Verify
against current code before trusting a specific line number.

## What it is
Much thinner on disk than the architecture map in root `CLAUDE.md` implies (that map lists
`helix/` and `frank/` subdirectories here that do not exist; an older copy lives in the
2026-08-19 consolidation snapshot under `archive/`). Actual contents:
- `intake/intake.sh` — Sector 4 vault intake (`intake.sh file|dir …`): checks the breach_coms4 mount, then calls `phoenix-core/tools/intake.py` per file. Bash (`#!/usr/bin/env bash` since 2026-09-29); the zsh-only glob was replaced by `find -print0` on 2026-09-21.
- `paging.py` — Linux AI paging manager (swapfiles via swapon/swapoff, predictive engine, loopback-only control API, kernel-Helix attach via libhelix) with the Doppelganger port, live-tested on pbm-compaq 2026-09-28. With the two named Helix instances on pbm-compaq (helix@ingress + helix@egress, since 2026-09-29) it reads them as one: libhelix adds up every live dm-helix device, and `/proc/helix` shows the hottest of the two.
- `paging_windows.py` — Windows pagefile twin (WMI; admin-only; not live-tested). Its expand/shrink/start need a reboot to take effect, so it cannot follow live load; superseded for Helix by `paging_helix.py` — retiring it is Jerry's call.
- `paging_helix.py` — the paging manager wired to the userspace Helix, one file for Windows and Linux (2026-10-03). LOAD: plugs into her Dandelion as its memory-pressure source — max(RAM in use, commit charge) — so her own tiered eviction (raw → zlib 5 → Strand B) follows the machine. EVICTION: watches Strand B fill velocity and spawns Doppelgangers (temporary, self-expiring Strand B budget extensions, sized from eviction speed, capped by free disk minus max(10%, 20 GB)) when B is ≥85% full, predicted full within 120 s, or she refused an allocation; retires them after 10 min once calm and her Strand B data fits without them. Never touches L1/L2/L3, never below her base Strand B. Last 50 decisions kept for `genie status`. Started by `sector1/kernel/main_kernel.py`; `clean_stale_strand_b()` clears Strand B dirs left by force-stopped kernels.
- `pcs.py` — Proximity Control String model (prefetch address/probability manifest, zipcodes, snap_clone).
- `vault/download.sh` — download URLs/packages into the vault CLONEPOOL (catalog-logged, SQL-escaped).
- `vault/phoenix-push.sh` — append-only rsync push into the vault CLONEPOOL (never overwrites, never deletes).

## Dependencies
None declared here. Runtime: bash, python3, sqlite3, rsync, curl/wget; `paging.py` needs root
for swap operations.

## Commands / entry points
- `sector4/intake/intake.sh file <path>` / `dir <path>` — reached through `usys intake`
  (`scripts/usys.ps1` `Get-UsysIntakeSh`). Needs breach_coms4 at `/mnt/g` and
  `phoenix-core/tools/intake.py`; for everyday clone-pool intake use `usys clone`
  (`sector2/package-handler/intake.sh`) instead.
- `sector4/vault/download.sh url|pkg|batch|status|help`, `sector4/vault/phoenix-push.sh push|status|help`.
- `paging_helix.py` has no CLI — `main_kernel.py:boot()` starts it; `genie status` shows pressure, Doppelgangers and decisions. `PHOENIX_PAGER_INTERVAL` (s, default 5), `PHOENIX_HELIX_B_MAX_MB` (hard Strand B cap).
- `python3 sector4/paging.py start` — run by `phoenix-paging.service` (/opt/phoenix) or
  `phoenix-helix-kernel.service` (Debian VM over the SMB share), see `sector3/services/`.

## Connects to / connected from
- `scripts/usys.ps1` → `sector4/intake/intake.sh` (`usys intake`, the Sector 4 path by design).
- `sector4/intake/intake.sh` → `phoenix-core/tools/intake.py` (per-file intake).
- `dashboard/main.js` → `sector4/intake/intake.sh` (folder browser + intake).
- `dashboard/main.js` pagefile panel mirrors `sector4/paging_windows.py`'s WMI approach (parallel logic, not an import).
- `sector4/vault/download.sh` → `sector2/unitedsys/core/us.py` (package seeding; resolved from `PHOENIX_ROOT` or the repo).
- `sector4/pcs.py` → `sector2/unitedsys` (`core.catalog`, repo-relative).
- `sector3/services/phoenix-paging.service` and `sector3/services/phoenix-helix-kernel.service` → `sector4/paging.py`.
- `sector4/paging.py` → `sector1/kernels/libhelix/helix.py` (kernel Helix state, summed over every live dm-helix device).
- `sector1/kernel/main_kernel.py` → `sector4/paging_helix.py` (`boot()` starts the pager on the userspace Helix).
- `sector4/paging_helix.py` → `sector1/helix/helix_vram.py` (`set_pressure_source`, `set_strand_b_budget`, `get_stats`; `machine_memory()` is its load reading).
- `sector3/services/phoenix-paging.service` → `sector3/services/helix@.service` (ordering only: paging starts after the Helix units, single or pair, but no longer pulls any of them in — changed 2026-09-29, because pulling in the single Helix stopped the ingress/egress pair).
- `sector3/worker-up/operations-set.txt` → `sector4/paging.py` (the road test ships it to a worker box with the rest of the Helix team).

## Known issues (verified, not guessed)
- **Two breach_coms mount conventions** (S34OPS-F22, needs Jerry): `intake.sh`, `download.sh`,
  `phoenix-push.sh`, root `status.sh`, `pcs.py` use the Debian-VM `/mnt/g` (`/mnt/d`)
  convention; `tools/align_dirs.sh` and the frankenhelix/propagator units use
  `/media/<user>/breach_comsN`. On the external Ubuntu target neither exists yet, so the
  vault scripts stop at "breach_coms4 not mounted".
- `pcs.py` defaults its pool to `/mnt/d/clonepool` (breach_coms1 under the VM convention)
  unless `CLONEPOOL`/`CLONEPOOL_DIR` is set — part of the same F22 decision.
- The old "line 59 is a bash syntax error (zsh glob)" issue is fixed; `usys doctor` checks
  code lines only and reports it green (the glob text survives only in a comment).
