# archive — fossil/consolidation dumps (inside Phoenix-DevOps-oS)

Written 2026-09-12. Verify against current code before trusting a specific line number.

Not to be confused with `D:\Users\jwlef\Phoenix\archive\` (a separate, sibling archive
folder outside this repo — see the root `Phoenix\CONNECTIONS.md` master index).

## What it is
Intentionally dead/historical storage: `20260607-140818/`, `20260607-141645/`,
`docs-consolidation-20260822-111531/` (old AUTHENTICATION/GETTING_STARTED/GLOBAL_COMMANDS/
QUICK_START docs), `fossil-consolidation-20260819-210541/` (largest, ~29MB — includes
`SECTOR4/copes/src/helix_legacy/helix_bridge.c`, the Helix kernel-module archaeology find),
`kali-import-consolidation-20260822-113129/`, `root-stale-consolidation-20260822-114018/`,
`oldarch.json`.

## Dependencies / commands / entry points
None — inert by design.

## Connects to / connected from
Nothing live calls into here. This directory is explicitly excluded from
`sector2/package-handler/intake.sh`'s `SKIP_DIRS` — it is deliberately NOT catalogued by
the live intake pipeline.

## Known issues (verified, not guessed)
**This whole directory is, by design, the "dead/historical" bucket for the rest of the
repo.** Treat everything in here as intentionally retired, not as a bug or a cleanup
target. Example: the resurrected `sector1/security/` guardian system was fossil-copied
here before being moved to its live home — the fossil copy was deliberately left in place
as history, not an oversight.
