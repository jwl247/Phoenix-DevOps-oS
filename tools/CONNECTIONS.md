# tools — utility scripts + PoC distro-boot sandbox

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F25/F28/F29/F31/F41/F42/F43); re-checked
2026-09-30 (dashboard DRIVER UPDATES button, PBM website logo from the video tools). Verify
against current code before trusting a specific line number.

## What it is
Local utilities, the tray app, and the distro-boot / Helix proof-of-concept sandbox.
- `clone.sh` — forwarder to `bin/clone` (OUT of the pool) since 2026-10-07; it used to be the old IN command (CMDWALK-F06).
- `clone.ps1` — legacy PowerShell `clone` that still puts files IN (intake). Not loaded by `install.ps1`; `usys.ps1`'s global `clone` (OUT) shadows it. Use `intake` for IN.
- `align_dirs.sh` — bash; creates the Phoenix directory layout on a Linux box (`--check` = audit only).
- `get_distros.sh` — downloads a list of Linux ISOs to a Ventoy folder (dated URLs, checks wget's own exit status).
- `backup_user_guide.md` — a parked restic/PyQt6 whole-system backup design (no code here implements it).
- `notation/phoenix-notation.html` — music notation transcriber (v3, self-contained, no network).
- `phoenix-tray.py` — system tray app: watches Downloads, intakes through `scripts/hsf-intake.sh`, launches suites.
- `phoenix-tray.spec` — PyInstaller spec for the tray (script path from `SPECPATH`).
- `phoenix-tray.suite.json` — the tray's suite manifest (runtime python + network → needs `usys suite-trust`).
- `driver-updater/driver-updater.ps1` — Windows driver updater. Part 1 checks Windows Update's own signed driver catalog through the PSWindowsUpdate module (installs it from the PowerShell Gallery on first run) and installs nothing without a yes; Part 2 names hardware Windows Update doesn't cover by its USB/PCI vendor ID and points at that vendor's own support page (nothing downloaded for you). Flags: `-WhatIfOnly` (report only), `-InstallAll`, `-ListCurrent`, `-SkipVendorScan`. Needs admin. UTF-8 with BOM, parses under PowerShell 5.1 and 7. Explained in `driver-updater/README.md`. Launched from the dashboard's DRIVER UPDATES button (new 2026-09-30) or run by hand.
- `video/` — local video tooling (`record-voice.ps1`, `setup-obs.py`, `pbm-channel-art.py`), hardcoded to the E: ops drive.
- `video/record-voice.ps1` — records Jerry's voice from the V8S sound card for a video (the phone records the picture); press Q to stop; files land in E:\Phoenix\video\raw.
- `video/setup-obs.py` — adds a "Phoenix" profile and scene collection to OBS Studio (screen + webcam, V8S mic, 1080p30 MP4, CPU x264 per the no-GPU rule). Run with OBS closed.
- `video/pbm-channel-art.py` — draws the PBM Consulting Service YouTube banner and profile picture in the website's colours and fonts (`python tools/video/pbm-channel-art.py [--out DIR]`, default E:\Phoenix\video\brand). Since 2026-09-30 `--logo <path>` also writes the website's stamp-and-name logo as a transparent PNG.
- `poc/` — the distro-boot / Helix sandbox: `debian-seed/`, `ubuntu-seed/` (cloud-init seeds), `*.suite.json` templates (debian, ubuntu, qemu-system, hello-phoenix, yt-dlp, steam, helix-poc, google), `run-debian.ps1`, `run-ubuntu.ps1`, `run-helix-poc.{ps1,sh}`, `start-debian-persist.ps1`, `setup-shared-fs.ps1`, `persist-smb-mount.sh`, `install-helix-autostart.ps1`, `test-double-helix.{cmd,ps1,sh}`, `true_double_helix.py`, `watch-downloads.ps1`, `demo-collab.{ps1,sh}`, and the plans/guides (`README.md`, `DOUBLE-HELIX-PLAN.md`, `HELIX-LIGHTNING-GUIDE.md`, `SHARED-FS-PLAN.md`).

## Dependencies
`tools/phoenix-tray.suite.json` + 8 `tools/poc/*.suite.json` — Phoenix's own suite-manifest
format (consumed by `usys run <name>` once cloned into the pool), not npm/pip manifests.
The tray needs `pystray pillow plyer` (+ optional `watchdog`) and Git for Windows' bash.

## Commands / entry points
- `tools/clone.sh <name> [vN] [folder]` → `bin/clone` (OUT). IN is `intake <file>` (`bin/intake`).
- `tools/poc/run-debian.ps1` → `usys run debian`; `tools/poc/start-debian-persist.ps1` → `usys run debian -Persist --share`.
- `tools/poc/install-helix-autostart.ps1` — registers the `Phoenix-HelixLightningKernel` logon task (elevated) or a Startup-folder fallback; called by repo-root `install.ps1`.
- `python tools/phoenix-tray.py [--auto-intake]`.
- `tools/poc/google.suite.json`, `steam.suite.json` use `runtime: external` — dashboard-launched only; `usys run` refuses that runtime.

## Connects to / connected from
- `tools/clone.sh` → `bin/clone` → `sector2/package-handler/intake.sh clone` (OUT).
- `bin/align_dirs` → `tools/align_dirs.sh`.
- `bin/get_distros` → `tools/get_distros.sh`.
- `tools/phoenix-tray.py` → `scripts/hsf-intake.sh` → `sector2/package-handler/intake.sh`.
- `tools/phoenix-tray.py` → `scripts/usys.ps1` (`usys run debian|ubuntu`).
- `tools/poc/true_double_helix.py` → `sector1/helix-lightning/franken5.py` (sys.path insert).
- `tools/poc/test-double-helix.ps1` → `sector4/paging.py` (copied to the SMB share for the VM).
- `dashboard/button-generator.js` → `dashboard/main.js` → `tools/driver-updater/driver-updater.ps1` (DRIVER UPDATES button → IPC `open-driver-updates` → opens the script in its own elevated PowerShell 7 window with a UAC prompt; fixed script path, no arguments from the page, Windows only). Added in the dashboard 2026-09-30; that dashboard change was not yet committed when this was written.
- `tools/video/pbm-channel-art.py` → `pbm-consulting-website/assets/logo.png` (the site's masthead logo is made by `--logo`).
- `install.ps1` → `tools/poc/install-helix-autostart.ps1` and, separately, `sector3/services/install-dashboard-windows.ps1` (the two Windows autostart legs).
- `tools/poc/README.md` documents the one-time setup (QEMU placement, qcow2 download) needed
  before `usys run debian`/`usys run ubuntu` resolves anything.

## Known issues (verified, not guessed)
- `tools/backup_user_guide.md`'s design is parked on purpose — don't "complete" it without Jerry.
- `helix-poc.suite.json`'s `entry` is now suite-relative (`true_double_helix.py`); a pool
  copy made from the older template still says `tools/poc/true_double_helix.py`.
- `get_distros.sh` pins dated ISO URLs that rotate off mirrors (move to a manifest — open).
- No ScriptForge leftovers here (moved to `sector2/apps/scriptforge/` 2026-09-05).
