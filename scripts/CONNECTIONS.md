# scripts — the global CLI (usys.ps1)

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
`usys.ps1` (~101KB) is the master PowerShell CLI for the whole project: clone/intake,
suite run (QEMU distros, PoC binaries), search, pull, the suite-execution security gate,
shared-filesystem import/export. `usys.cmd` is a thin Windows cmd wrapper. Also here:
`usys-suite-gate.Tests.ps1` (16/16 passing suite-gate tests), `intake.ps1` (Windows
intake wrapper).

## Dependencies
None (pure PowerShell/cmd, no package.json).

## Commands / entry points
Load with `. .\scripts\usys.ps1` then call `usys <command>`, or via `bin/usys` (dot-sources
this through pwsh). Key subcommands: `usys status`, `usys list-suites`, `usys clone`,
`usys intake` (currently mis-routed — see Known issues), `usys run <suite> [--accel
auto|tcg|whpx|hyperv|kvm] [--share] [--unverified]`, `usys search`, `usys pull`,
`usys fs-import`/`fs-export`, `usys suite-trust <name>`, `usys download`, `usys watch`.

## Connects to / connected from
- `usys.ps1` (~line 160) → `sector2/package-handler/intake.sh` — the canonical clone path.
- `usys.ps1` (~line 147) → `sector4/intake/intake.sh` — the broken/mis-wired path used by
  `usys intake` (not `usys clone`).
- 4 call sites (`usys distro intake-qemu`, `usys download`, `usys watch`,
  `Get-UsysWatcherPending`) still call the deprecated `phoenix-core/tools/intake.py`
  instead of the canonical bash pipeline.
- `usys run` reads suite manifests from the **clonepool** (`$env:CLONEPOOL_DIR`, currently
  `E:/Phoenix/clonepool`), not from `tools/poc/*.suite.json` directly — those are templates
  that must be `usys clone`d into the pool first.
- Called by `bin/*` wrappers, `tools/clone.sh`/`clone.ps1`, and the dashboard's env reads.

## Known issues (verified, not guessed)
- **`usys run debian` fails live** with `The requested operation requires elevation.`
  during accelerator resolution (the `auto`→`whpx`/`hyperv` block, ~lines 1267-1380).
  Reproduced 2026-09-12, not yet root-caused or fixed — see memory
  `phoenix-debian-boot-elevation-bug` for full detail and next diagnostic step
  (try `--accel tcg` explicitly).
- `usys intake` mis-routes to `sector4/intake/intake.sh` (which has its own bash-syntax
  bug) instead of the canonical `sector2/package-handler/intake.sh`. Use `usys clone` as
  the working substitute until this is repointed.
- 4 sites still call the deprecated Python intake (`phoenix-core/tools/intake.py`) — see
  above; needs a shared `Invoke-UsysIntakeFile` helper repointing all 5 call sites at once
  (per CLAUDE.md's own NEXT SESSION notes).
