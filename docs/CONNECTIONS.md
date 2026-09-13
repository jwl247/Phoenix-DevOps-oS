# docs — documentation

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
Markdown docs: `GITHUB_SETUP.md`, `GLOSSARY.md`, `LOL_INSTALLER.md`,
`PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md` (the **previous** attempt at a connections
doc — see Known issues), `SECRETS.md` (pointer only, real values live in
`F:\Phoenix\Vault\secrets\`), `SUITE_EXECUTION_GATE.md`, `SUITE_MANIFEST.md`, per-sector
READMEs (`docs/sector1..4/README.md`, `docs/sector2/CLONE.md`), `docs/config/README.md`,
`docs/systemd/README.md`. Also a batch of recovered claude.ai conversation transcripts
(`.txt` files) that were sources for real features — e.g.
`config centralizer canner manager.txt` → `dashboard/config-centralizer.js`,
`sec audit doc from you to you.txt` → the whole Security & Integrity Audit backlog in root
`CLAUDE.md`, `yellowbrickroad.txt` → the Helix kernel-module archaeology finding.

## Dependencies
None (pure docs).

## Commands / entry points
None (pure docs).

## Connects to / connected from
`docs/PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md` was meant to be the master
cross-directory connections doc but contains a known-stale reference (see Known issues) —
**this CONNECTIONS.md system (this file + the per-directory ones + the root index)
supersedes it.** Don't delete the old file without checking with Jerry, but don't trust it
either.

## Known issues (verified, not guessed)
- `PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md` points at `sector3/workers/packages-worker/`
  as if it were live — it's a stale, dead duplicate (see `sector3/CONNECTIONS.md`). The
  real worker is `sector2/package-handler/worker/index.js`.
- `docs/lockdown motion.txt` (504 lines) is explicitly flagged in root CLAUDE.md as "never
  actually read" — still true as of this writing.
- QUICK_START.md/GETTING_STARTED.md vs root README.md overlap was flagged as "unaudited" —
  note these two files actually live under
  `archive/docs-consolidation-20260822-111531/`, not in live `docs/`, so the overlap may
  already be resolved; worth confirming rather than assuming either way.
