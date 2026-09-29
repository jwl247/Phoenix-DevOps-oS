# docs — documentation

Written 2026-09-12; inventory refreshed 2026-09-29 (round-2 audit XCUT-F27: 52 tracked files
per `git ls-files docs`). Verify against current code before trusting a specific line number.

## What it is
Markdown docs plus a batch of recovered claude.ai conversation transcripts. Top-level files
and one line per subfolder:

- `ATLAS.md` — how the Atlas "snow globe" lookup is built from these CONNECTIONS.md files
- `GITHUB_SETUP.md` — publishing/forking notes for the repo
- `GLOSSARY.md` — the D1 glossary routes and how to query them
- `LOL_INSTALLER.md` — the `lol` bootstrap installer
- `MONSTER_PHOENIX_IMPLEMENTATION.md` — how the Monster Phoenix game maps onto Phoenix infra
- `PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md` — historical 2026-06-30 snapshot, superseded (banner at top)
- `README.md` — the four-sector corridor design doc (design intent, banner at top)
- `SECRETS.md` — secrets map, names only; values live in `F:\Phoenix\Vault\secrets\`
- `SUITE_EXECUTION_GATE.md` — the `usys run` consent + audit gate
- `SUITE_MANIFEST.md` — the suite manifest format
- `compliance/` — FAR 52.204-21, NIST 800-171/CMMC and SOC2/ISO 27001 scorecards; `shared/` policies (governance, incident response, risk-assessment schedule, personnel, training); `pentest/` program (PROTOCOL.md, README.md, dated round reports — filed reports are never edited)
- `config/` — README for the design-era config layout (banner at top)
- `helix/` — BENCHMARKS.md, every measured Helix number with its source and conditions
- `history/` — SESSION-LOG.md, BUILD-STATUS-DETAIL.md, NEXT-SESSION-BACKLOG.md (moved out of root CLAUDE.md 2026-09-27)
- `plans/` — day-by-day-2026-09.md, helix-drive-plan.md, phoenix-portal-plan.md
- `sector1/` — sector 1 corridor README (design intent; real inventory is `sector1/CONNECTIONS.md`)
- `sector2/` — sector 2 corridor README + CLONE.md (the `usys clone` intake guide)
- `sector3/` — sector 3 corridor README (design intent)
- `sector4/` — sector 4 corridor README (design intent)
- `systemd/` — README for the unit files (units live in `sector3/services/`)

The 11 `.txt` files are raw recovered transcripts that were sources for real features:
`automated scheduler.txt`, `config centralizer canner manager.txt` (→
`dashboard/config-centralizer.js`), `config widget gui.txt`, `file motion module.txt`,
`lockdown motion.txt`, `master image manager.txt`, `master_image_widget.txt`,
`master_widget_install.txt`, `sec audit doc from you to you.txt` (→ the Security &
Integrity Audit backlog, now in `docs/history/NEXT-SESSION-BACKLOG.md`), `the whole
thing.txt`, `yellowbrickroad.txt` (→ the Helix kernel-module archaeology finding).

## Dependencies
None (pure docs).

## Commands / entry points
None (pure docs). After editing any CONNECTIONS.md, refresh Atlas per root `CLAUDE.md`
SESSION PROTOCOL (`node parse-connections.js` in `sector2/package-handler/`).

## Connects to / connected from
`docs/ATLAS.md` describes `sector2/package-handler/parse-connections.js`, which reads this file.
`docs/SECRETS.md` maps names to `F:\Phoenix\Vault\secrets\`.
`docs/compliance/pentest/PROTOCOL.md` governs the daily rounds filed in `docs/compliance/pentest/`.
`docs/history/SESSION-LOG.md` is where root `CLAUDE.md` sends session history.
`docs/PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md` was the previous connections attempt;
**this CONNECTIONS.md system (this file + the per-directory ones + the root index)
supersedes it.** Don't delete the old file without checking with Jerry, but don't trust it.

## Known issues (verified, not guessed)
- `lockdown motion.txt` (504 lines) has still never been reviewed — tracked in
  `docs/history/NEXT-SESSION-BACKLOG.md`.
- The corridor READMEs (`README.md`, `sector1-4/README.md`, `config/README.md`,
  `systemd/README.md`) describe design intent, not the live tree; each carries a banner.
