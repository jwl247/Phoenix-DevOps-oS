# scripts — the global CLI (usys.ps1) and the intake entry points

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F26/F39, CONN-F07/F08/F20). Verify against
current code before trusting a specific line number.

## What it is
The master PowerShell 7 CLI for the whole project plus the scripts that feed the clone pool.
- `usys.ps1` — ~120 KB / ~2 730 lines. clone/intake, suite run (QEMU distros, PoC binaries) behind the suite-execution gate, search, pull/open (SHA3-512-verified against D1 custody since 2026-09-29), shared-filesystem import/export, doctor/status.
- `usys.cmd` — thin Windows cmd shim (`-File usys.ps1 %*`, never `-Command`).
- `usys-suite-gate.Tests.ps1` — standalone (no Pester) execution-gate tests, 18/18 passing.
- `hsf-intake.sh` — non-interactive intake of files/folders straight into `sector2/package-handler/intake.sh`; resolves PHOENIX_AUTH / PHOENIX_WORKER_URL / CLONEPOOL_DIR / CF-Access from the Windows User environment. CLAUDE.md's named intake path.
- `intake.ps1` — Windows intake wrapper (PowerShell 7 only).
- `compliance-local-check.ps1` — local half of the monthly compliance routine (Defender status etc., FAR 52.204-21 controls 13-15).
- `install-compliance-check-autostart.ps1` — registers the weekly `Phoenix-ComplianceCheck` task.

## Dependencies
PowerShell 7 (`#Requires -Version 7.0`), Git for Windows' bash (intake pipeline), and for
SHA3 verification either .NET SHA3 support (Windows 11) or python3. No package manifests.

## Commands / entry points
Load with `. .\scripts\usys.ps1` then `usys <command>`, or via `bin/usys` / `bin/usys.cmd` /
`scripts/usys.cmd` (all `-File`, arguments passed verbatim). Subcommands:
`init`, `status`, `doctor`, `version`, `path-register`, `help`, `intake` (Sector 4 vault
pipeline, by design), `clone` (OUT of the Sector 2 pool — runs `bin/clone`), `search`, `download`, `watch
start|stop|pending|status`, `open <name>.lol` / `pull <name>` (R2 bytes, SHA3-512 checked
against D1, refused on mismatch), `run <suite> [--accel auto|tcg|whpx|hyperv|kvm] [--share]
[--unverified] [--dry-run]`, `suite-trust`, `list-suites`/`suite-list`, `suite-promote`,
`load`, `distro list|fetch-qemu|intake-qemu`, `fs-init`, `fs-ls`, `fs-import`, `fs-export`,
`fs-sync`. The legacy registry verbs (`register`, `call`, `swap`, `rollback`, `list`, `info`,
`remove`, `where`, `sync`) are not implemented in this repo — they only delegate to an
external `usys.sh` named by `USYS_ENGINE`, and say so.

Bash side: `bash scripts/hsf-intake.sh <path> [<path> ...]`.

## Connects to / connected from
- `scripts/usys.ps1` → `sector2/package-handler/intake.sh` — IN: `usys download`, `usys watch`, `usys distro intake-qemu` (all via `Invoke-UsysIntakeFile`; no call site uses `phoenix-core/tools/intake.py` any more).
- `scripts/usys.ps1` → `bin/clone` → `intake.sh clone` — OUT: `usys clone` (`Invoke-UsysCloneOut`).
- `scripts/usys.ps1` → `sector4/intake/intake.sh` — `usys intake` / `.lol` magic extension (the Sector 4 vault pipeline; routed there on purpose).
- `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh` (piped, non-interactive).
- `tools/phoenix-tray.py` → `scripts/hsf-intake.sh` (tray intake, since 2026-09-29).
- `scripts/usys.ps1` → `sector2/package-handler/worker/index.js` (`/clonepool` GETs for search/pull, `?meta=true` for the custody hash).
- `scripts/usys.ps1` → `sector1/security/` (CoPES guardian events on gate refusals).
- `bin/usys`, `bin/run`, `bin/clone.cmd`, `scripts/usys.cmd` → `scripts/usys.ps1` (`-File`).
- `install.ps1` → `scripts/` (PATH registration of `usys.cmd`).
- `usys run` reads suite manifests from the clone pool (`$env:CLONEPOOL_DIR`), not from
  `tools/poc/*.suite.json` directly — those are templates that must be `intake`d first.

## Known issues (verified, not guessed)
- `CLONEPOOL_DIR` drift: the User env points at `E:/Phoenix/clonepool` (no suites) while the
  real pool with `debian/ubuntu/qemu-system` is `F:\Phoenix\clonepool`, so `usys run debian`
  says "Suite not found" from a fresh terminal (S34OPS-F02 — Jerry's call).
- The old "`usys run debian` fails with requires elevation" issue is gone (try/catch → tcg
  fallback), and the sector4 intake zsh-glob bug is fixed (`find -print0`, 2026-09-21);
  `usys doctor` now checks code lines only and flags a regression in red.
- `[version]` sorts vs `version = 'v1'` stamps (S34OPS-F17) still open.
