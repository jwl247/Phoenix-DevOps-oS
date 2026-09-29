# tools — utility scripts + PoC distro-boot sandbox

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F25/F28/F29/F31/F41/F42/F43). Verify against
current code before trusting a specific line number.

## What it is
Local utilities, the tray app, and the distro-boot / Helix proof-of-concept sandbox.
- `clone.sh` — bash clone wrapper called by `bin/clone`; runs `sector2/package-handler/intake.sh` (in-repo only).
- `clone.ps1` — PowerShell clone wrapper (same pipeline); shadowed by `usys.ps1`'s global `clone` when both are loaded.
- `align_dirs.sh` — bash; creates the Phoenix directory layout on a Linux box (`--check` = audit only).
- `get_distros.sh` — downloads a list of Linux ISOs to a Ventoy folder (dated URLs, checks wget's own exit status).
- `backup_user_guide.md` — a parked restic/PyQt6 whole-system backup design (no code here implements it).
- `notation/phoenix-notation.html` — music notation transcriber (v3, self-contained, no network).
- `phoenix-tray.py` — system tray app: watches Downloads, intakes through `scripts/hsf-intake.sh`, launches suites.
- `phoenix-tray.spec` — PyInstaller spec for the tray (script path from `SPECPATH`).
- `phoenix-tray.suite.json` — the tray's suite manifest (runtime python + network → needs `usys suite-trust`).
- `driver-updater/driver-updater.ps1` — Windows driver updates via PSWindowsUpdate (UTF-8 with BOM, parses under 5.1 and 7).
- `video/` — local video tooling (`record-voice.ps1`, `setup-obs.py`, `pbm-channel-art.py`), hardcoded to the E: ops drive.
- `poc/` — the distro-boot / Helix sandbox: `debian-seed/`, `ubuntu-seed/` (cloud-init seeds), `*.suite.json` templates (debian, ubuntu, qemu-system, hello-phoenix, yt-dlp, steam, helix-poc, google), `run-debian.ps1`, `run-ubuntu.ps1`, `run-helix-poc.{ps1,sh}`, `start-debian-persist.ps1`, `setup-shared-fs.ps1`, `persist-smb-mount.sh`, `install-helix-autostart.ps1`, `test-double-helix.{cmd,ps1,sh}`, `true_double_helix.py`, `watch-downloads.ps1`, `demo-collab.{ps1,sh}`, and the plans/guides (`README.md`, `DOUBLE-HELIX-PLAN.md`, `HELIX-LIGHTNING-GUIDE.md`, `SHARED-FS-PLAN.md`).

## Dependencies
`tools/phoenix-tray.suite.json` + 8 `tools/poc/*.suite.json` — Phoenix's own suite-manifest
format (consumed by `usys run <name>` once cloned into the pool), not npm/pip manifests.
The tray needs `pystray pillow plyer` (+ optional `watchdog`) and Git for Windows' bash.

## Commands / entry points
- `tools/clone.sh <file>` / `. tools/clone.ps1; clone <file>` → `sector2/package-handler/intake.sh`.
- `tools/poc/run-debian.ps1` → `usys run debian`; `tools/poc/start-debian-persist.ps1` → `usys run debian -Persist --share`.
- `tools/poc/install-helix-autostart.ps1` — registers the `Phoenix-HelixLightningKernel` logon task (elevated) or a Startup-folder fallback; called by repo-root `install.ps1`.
- `python tools/phoenix-tray.py [--auto-intake]`.
- `tools/poc/google.suite.json`, `steam.suite.json` use `runtime: external` — dashboard-launched only; `usys run` refuses that runtime.

## Connects to / connected from
- `bin/clone` → `tools/clone.sh` → `sector2/package-handler/intake.sh`.
- `bin/align_dirs` → `tools/align_dirs.sh`; `bin/get_distros` → `tools/get_distros.sh`.
- `tools/phoenix-tray.py` → `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh`.
- `tools/phoenix-tray.py` → `scripts/usys.ps1` (`usys run debian|ubuntu`).
- `tools/poc/true_double_helix.py` → `sector1/helix-lightning/franken5.py` (sys.path insert).
- `tools/poc/test-double-helix.ps1` → `sector4/paging.py` (copied to the SMB share for the VM).
- `install.ps1` → `tools/poc/install-helix-autostart.ps1` and, separately, `sector3/services/install-dashboard-windows.ps1` (the two Windows autostart legs).
- `tools/poc/README.md` documents the one-time setup (QEMU placement, qcow2 download) needed
  before `usys run debian`/`usys run ubuntu` resolves anything.

## Known issues (verified, not guessed)
- `tools/backup_user_guide.md`'s design is parked on purpose — don't "complete" it without Jerry.
- `helix-poc.suite.json`'s `entry` is now suite-relative (`true_double_helix.py`); a pool
  copy made from the older template still says `tools/poc/true_double_helix.py`.
- `get_distros.sh` pins dated ISO URLs that rotate off mirrors (move to a manifest — open).
- No ScriptForge leftovers here (moved to `sector2/apps/scriptforge/` 2026-09-05).
