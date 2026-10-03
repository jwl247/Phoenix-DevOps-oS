# scripts — the global CLI (usys.ps1) and the intake entry points

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F26/F39, CONN-F07/F08/F20). Verify against
current code before trusting a specific line number.

## What it is
The master PowerShell 7 CLI for the whole project plus the scripts that feed the clone pool.
- `usys.ps1` — ~120 KB / ~2 730 lines. clone/intake, suite run (QEMU distros, PoC binaries) behind the suite-execution gate, search, pull/open (SHA3-512-verified against D1 custody since 2026-09-29), shared-filesystem import/export, doctor/status.
- `phx-kernel.ps1` — the universal kernel for a PS7 profile (2026-10-02). Standalone: no repo, no usys, no Python. A command you type that this machine lacks is looked up in the clone pool by hex id (`<name>.ps1/.exe/.py/.js/.sh`), pulled from R2, SHA3-512-checked against D1 custody, asked once, cached under `~/.phoenix/kernel`, then run from cache offline while the hash still matches. Built-in portable SHA3 for OS builds without it. `bingo status|list|forget|refresh|log|update`; `pwsh -File phx-kernel.ps1 install`.
- `phx-kernel.Tests.ps1` — standalone kernel tests against a stand-in pool, 43/43 (incl. the preload closet and -Yes).
- `genie.ps1` — plain English in, one tool from a library out (2026-10-03). Local Ollama (llama3.2:3b) answers only in a fixed JSON shape with the tool limited to the library (H.L.K's constrained-decoding trick); auto tools run, ask tools wait for a yes; no model = word match + always asks. Commands run through the universal kernel (pulled + SHA3-checked if missing). `genie learn|library|forget|log`. Named `genie` so the kernel can pull it from the pool by typing `genie`.
- `genie.Tests.ps1` — stand-in model, 17/17. `genie install` puts kernel-adjacent copies of genie + radar in the PS7 profile and teaches the four Radar tools.
- `radar.ps1` — Set-Aside Radar from the desktop/CLI (2026-10-03): `radar new|week [client]|clients|runs`, read-only, over the live worker's admin routes (`/subscribers`, `/preview`, `/runs`) with PHOENIX_AUTH from env or `~/.phoenix/kernel.env`.
- `radar.Tests.ps1` — stand-in worker fed rows copied from the live `pbm_radar_db`, 7/7.
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
pipeline, by design), `clone` (Sector 2 pipeline), `search`, `download`, `watch
start|stop|pending|status`, `open <name>.lol` / `pull <name>` (R2 bytes, SHA3-512 checked
against D1, refused on mismatch), `run <suite> [--accel auto|tcg|whpx|hyperv|kvm] [--share]
[--unverified] [--dry-run]`, `suite-trust`, `list-suites`/`suite-list`, `suite-promote`,
`load`, `distro list|fetch-qemu|intake-qemu`, `fs-init`, `fs-ls`, `fs-import`, `fs-export`,
`fs-sync`. The legacy registry verbs (`register`, `call`, `swap`, `rollback`, `list`, `info`,
`remove`, `where`, `sync`) are not implemented in this repo — they only delegate to an
external `usys.sh` named by `USYS_ENGINE`, and say so.

Bash side: `bash scripts/hsf-intake.sh <path> [<path> ...]`.

## Connects to / connected from
- `scripts/usys.ps1` → `sector2/package-handler/intake.sh` — `usys clone`, `usys download`, `usys watch`, `usys distro intake-qemu` (all via `Invoke-UsysIntakeFile`; no call site uses `phoenix-core/tools/intake.py` any more).
- `scripts/usys.ps1` → `sector4/intake/intake.sh` — `usys intake` / `.lol` magic extension (the Sector 4 vault pipeline; routed there on purpose).
- `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh` (piped, non-interactive).
- `tools/phoenix-tray.py` → `scripts/hsf-intake.sh` (tray intake, since 2026-09-29).
- `scripts/usys.ps1` → `sector2/package-handler/worker/index.js` (`/clonepool` GETs for search/pull, `?meta=true` for the custody hash).
- `scripts/genie.ps1` → `scripts/phx-kernel.ps1` (runs a tool's command through the kernel) and → Ollama `127.0.0.1:11434/api/chat` (local model only).
- `scripts/radar.ps1` → `pbm-consulting-website/radar-worker/index.js` (admin GET routes only; never sends, changes or charges).
- `scripts/phx-kernel.ps1` → `sector2/package-handler/worker/index.js` (`GET /clonepool/<hex>?meta=true` for the custody row, `GET /clonepool/<hex>` for the R2 bytes; read-only, never writes).
- `scripts/usys.ps1` → `sector1/security/` (CoPES guardian events on gate refusals).
- `bin/usys`, `bin/run`, `bin/clone.cmd`, `scripts/usys.cmd` → `scripts/usys.ps1` (`-File`).
- `install.ps1` → `scripts/` (PATH registration of `usys.cmd`).
- `usys run` reads suite manifests from the clone pool (`$env:CLONEPOOL_DIR`), not from
  `tools/poc/*.suite.json` directly — those are templates that must be `usys clone`d first.

## Known issues (verified, not guessed)
- `CLONEPOOL_DIR` drift: the User env points at `E:/Phoenix/clonepool` (no suites) while the
  real pool with `debian/ubuntu/qemu-system` is `F:\Phoenix\clonepool`, so `usys run debian`
  says "Suite not found" from a fresh terminal (S34OPS-F02 — Jerry's call).
- The old "`usys run debian` fails with requires elevation" issue is gone (try/catch → tcg
  fallback), and the sector4 intake zsh-glob bug is fixed (`find -print0`, 2026-09-21);
  `usys doctor` now checks code lines only and flags a regression in red.
- `[version]` sorts vs `version = 'v1'` stamps (S34OPS-F17) still open.
