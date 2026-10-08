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
- `phoenix-rotate.ps1` — `rotate-key`: auth rotation, the whole chain in one command (Jerry's SID + typed ROTATE, never an agent). Step 1 `sector2/package-handler/rotate-phoenix-auth.sh` (new PHOENIX_AUTH → packages-worker, office-notify-worker, pbm-radar-worker, each proven on /whoami → Windows user env via setx → every vault file with a `PHOENIX_AUTH=` line except templates/backups). Step 1b `rotate-access-token.sh` (Cloudflare Access secret, 1 h overlap). Step 2 `phoenix_vault.py push` (cloud vault). Step 3 refreshes this window only.
- **Where the keys live (single source of truth, 2026-10-08):** the vault `F:\Phoenix\Vault\secrets\phoenix-secrets.env` + Windows user env (HKCU). Every program inherits HKCU. `~/.phoenix_env.sh` / `.ps1` hold NO keys anymore (they had a stale Sep-24 key that overrode the live one in bin/clone, bin/intake, intake.ps1 → "PHOENIX_AUTH REJECTED"). `install.ps1` takes keys from the vault (vault wins), never writes them into those files.
- **Who gets a rotated key:** automatic — new PS7 windows (profile), usys, genie, hsf-intake, every bin/ command, HUD (`AtlasClient` reads HKCU per call), portal (re-reads the vault per call). Needs a restart — dashboard, the running kernel (genie_control), PhoenixPortal/Hands tasks, open shells. By hand — pbmIII and awslh (`phoenix_vault.py pull --keys PHOENIX_AUTH,…` into `/etc/phoenix/secrets`); Linux `install.sh` still writes the key into `~/.phoenix_env.sh` there. Separate keys, not rotated by rotate-key — worker-up data planes (`~/.phoenix/worker-up/<name>/auth`), the mesh (`MESH_ADMIN`).
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
- **The easy commands (2026-10-08, Jerry: "usys is the new common command", one word):** `usys intakeS <file>` (a suit IN: Sector 2 intake + custody must hold these bytes, via genie's `Invoke-GenieIntakeLocal`) · `usys intakeC <file|folder|url>` (clone pool IN: `Invoke-UsysIntakeFile` → `sector2/package-handler/intake.sh`; a GOG/program folder → app-intake) · `usys import <suit>` and bare `usys <suit>.py` (the import method: `genie import` → kernel R2 → RAM → run) · `usys get <name|folder/name>` (OUT: `bin/clone`) · `usys run` · `usys closet` / `start` / `stop` / `log` (genie verbs) · `usys jump` (= `g`, PS7 window only) · `usys status` (usys + kernel) · `usys help`. Genie works underneath (`Invoke-UsysKernel`); nobody types it.
- `usys intake` and `.lol` (existing file) now go to the Sector 2 clone pool too. `sector4/intake/intake.sh` (Sector 4 vault: needs `/mnt/g` = breach_coms4 inside the Debian VM, runs the deprecated `phoenix-core/tools/intake.py`) is no longer called from usys — it could never run from Windows/Git Bash (verified 2026-10-08).
- `usys list` is NOT the suite list: it goes to the legacy `usys.sh` delegate (not shipped). The suits are `usys closet`; runnable apps/VMs are `usys list-suites`.
- `scripts/phoenix-rotate.ps1` → `sector2/package-handler/rotate-phoenix-auth.sh` + `rotate-access-token.sh` → workers (`wrangler secret`), HKCU, vault files; → `scripts/phoenix_vault.py push` → `phoenix-vault-worker` (cloud vault, backups never pushed).
- `sector2/package-handler/intake.sh` preflight → `/whoami`: 401 = PHOENIX_AUTH wrong (REJECTED); 3xx/403 = Cloudflare Access keys wrong (ACCESS REFUSED); both stop before touching files.
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
