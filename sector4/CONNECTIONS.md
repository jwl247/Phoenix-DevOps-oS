# sector4 — Helix/Frank core engine, vault

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
Much thinner on disk than the architecture doc in root `CLAUDE.md` implies (that doc
describes `helix/` and `frank/` subdirectories here that don't currently exist — likely
relocated; a fossil copy lives under `archive/fossil-consolidation-20260819-210541/SECTOR4/`).
Actual current contents: `intake/intake.sh` (separate, currently-broken vault intake
pipeline — see Known issues), `paging.py`, `paging_windows.py`, `pcs.py`,
`vault/download.sh`, `vault/phoenix-push.sh`.

## Dependencies
None found (no package.json/requirements.txt/wrangler config in this directory).

## Commands / entry points
- `sector4/intake/intake.sh <cmd>` — **currently broken**, do not use (see Known issues).
  Use `sector2/package-handler/intake.sh` via `usys clone` instead — that is the canonical
  pipeline.
- `sector4/vault/phoenix-push.sh`, `sector4/vault/download.sh` — vault push/pull, not
  deeply audited this pass.

## Connects to / connected from
- `scripts/usys.ps1` (~line 147) references `sector4/intake/intake.sh` as a candidate path
  — this is the mis-wiring that makes `usys intake` route here instead of to the working
  pipeline.
- `dashboard/main.js` pagefile-management code is a JS reimplementation modeled on
  `sector4/paging_windows.py`'s WMI approach (not a direct import — parallel logic).
- `dashboard/main.js` (~line 374) references `SECTOR4` (see sector3's CONNECTIONS.md for
  the casing-bug detail).

## Known issues (verified, not guessed)
- **`sector4/intake/intake.sh` line 59 is a confirmed bash syntax error** — it uses a zsh
  extended glob (`"${target}"/**/*(.)`) inside a `#!/usr/bin/env bash` script. This is why
  `usys intake` currently fails/mis-behaves; `usys clone` is the working canonical path and
  does not go through this file.
- Root `CLAUDE.md`'s sector4 architecture description (expects `helix/` and `frank/`
  subdirectories) does not match what's actually on disk here — treat the architecture doc
  as aspirational/historical for this sector specifically, not current-state truth.
