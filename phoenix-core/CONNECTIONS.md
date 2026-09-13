# phoenix-core — standalone C intake engine

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
A standalone C project ("phoenix-helix-c") — `Makefile`, `libhelix.a`,
`src/*.c` (helix_core/diagnostics/ingress/egress/http), `tools/intake.py` (a legacy
Python intake pipeline), `tools/main.c` → the `phoenix-intake` CLI binary.

## Dependencies
C toolchain (`Makefile`-driven build) + Python 3 for `tools/intake.py`.

## Commands / entry points
- `make` in `phoenix-core/` — builds `libhelix.a` and the `phoenix-intake` CLI.
- `phoenix-core/tools/intake.py` — **deprecated**, carries a loud deprecation banner +
  stderr warning (added commit `686dc37`). Do not add new callers.

## Connects to / connected from
`scripts/usys.ps1` still has **4 call sites** calling `phoenix-core/tools/intake.py`
instead of the canonical bash pipeline: `usys distro intake-qemu`, `usys download`,
`usys watch` (inside a `Start-Job` scriptblock — the tricky one to fix, since the bash
path + `CLONEPOOL_DIR` must cross the job boundary), `Get-UsysWatcherPending`.

## Known issues (verified, not guessed)
- `phoenix-core/tools/intake.py` has **no R2 upload, no integrity baseline, and a stub
  QR sidecar** (`qr:sha3:` placeholder) — it predates all of the 2026-08+ integrity/R2
  work that the canonical `sector2/package-handler/intake.sh` has. Anything intaked
  through this path is missing real custody guarantees.
- Root `dashboard/manual/PHOENIX_MANUAL.md` (lines ~353/431) documents `cd phoenix-core &&
  make intake` and says "do not mix Python intake and C phoenix-core" — worth reconciling
  once the `usys.ps1` repoint (see `scripts/CONNECTIONS.md`) actually happens.
