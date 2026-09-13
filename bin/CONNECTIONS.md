# bin — global CLI wrappers

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
7 commands × {bash, `.cmd`} = 14 files: `run`, `status`, `clone`, `intake`, `usys`,
`align_dirs`, `get_distros`. Installed onto PATH by the repo-root installer so these work
as global terminal commands.

## Dependencies
None — thin shims only.

## Commands / entry points
Each file in this directory IS an entry point once installed on PATH.

## Connects to / connected from
- `bin/usys` → `scripts/usys.ps1` (primary) or `scripts/usys.sh` (fallback — **does not
  exist on disk**, dead fallback branch, harmless since the primary always resolves).
- `bin/clone` → `tools/clone.sh` → `sector2/package-handler/intake.sh`.
- `bin/intake` — comment in the file explicitly disambiguates: same pipeline as
  `bin/clone`; Sector 4 vault intake is a separate thing entirely, reached via `usys ...`
  directly, not through `bin/intake`.
- `bin/run` → suite execution (`usys run`, via `scripts/usys.ps1`).
- `bin/status` → repo status (root `status.sh` or `usys status` — not fully traced this
  pass, low priority).

## Known issues (verified, not guessed)
- `bin/usys`'s fallback to `scripts/usys.sh` is dead — that file doesn't exist (only
  `.ps1`/`.cmd` do). Harmless today because the primary candidate always resolves first,
  but worth removing the dead branch if this file is ever touched for other reasons.
