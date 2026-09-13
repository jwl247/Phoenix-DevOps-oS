# tools — utility scripts + PoC distro-boot sandbox

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
- `clone.ps1`/`clone.sh` — the clonepool intake wrapper called by `bin/clone`.
- `align_dirs.sh`, `get_distros.sh` — not deeply audited this pass.
- `backup_user_guide.md` — a parked restic/PyQt6 whole-system backup design; backend
  (`RotatingMasterImage`, `BackupScheduler`) is real, GUI/installer pieces are deliberately
  incomplete (mock wiring) — parked, not broken.
- `notation/phoenix-notation.html` — music notation transcriber (v3).
- `phoenix-tray.py`/`.spec`/`.suite.json` — system tray app + PyInstaller packaging.
- `poc/` — the distro-boot sandbox: `debian-seed/`, `ubuntu-seed/` (cloud-init seeds),
  `*.suite.json` manifests (debian, ubuntu, qemu-system, hello-phoenix, yt-dlp, steam,
  helix-poc, google), `run-debian.ps1`/`run-ubuntu.ps1`/`run-helix-poc.*`,
  `start-debian-persist.ps1`, `setup-shared-fs.ps1`, `install-helix-autostart.ps1`,
  `demo-collab.ps1`/`.sh`, `README.md` (the actual how-to for booting Debian/Ubuntu — read
  this before touching the VM boot path).

## Dependencies
`tools/phoenix-tray.suite.json` + 8 `tools/poc/*.suite.json` files — Phoenix's own "suite
manifest" format (consumed by `usys run <name>`), not npm/pip manifests.

## Commands / entry points
- `tools/clone.sh`/`clone.ps1` → calls `sector2/package-handler/intake.sh` (confirmed,
  `clone.sh` line 19).
- `tools/poc/run-debian.ps1` → `usys run debian` (see `scripts/CONNECTIONS.md` for the
  current live-failure state of this).
- `tools/poc/start-debian-persist.ps1` → `usys run debian -Persist --share` (the
  persistent + shared-filesystem boot mode).
- `tools/poc/install-helix-autostart.ps1` — called directly by repo-root `install.ps1`.
- `tools/phoenix-tray.py` — standalone tray app, packaged via `phoenix-tray.spec`.

## Connects to / connected from
- `install.ps1` (repo root) → `tools/poc/install-helix-autostart.ps1` (Windows Helix
  autostart) and, separately, `sector3/services/install-dashboard-windows.ps1` (dashboard
  autostart) — these are the two autostart legs, currently run as separate manual steps.
- `tools/poc/README.md` documents the full one-time setup (QEMU binary placement, Debian/
  Ubuntu qcow2 download) required before `usys run debian`/`usys run ubuntu` will resolve
  anything — read it before assuming a suite "isn't set up."

## Known issues (verified, not guessed)
- `tools/backup_user_guide.md`'s design is explicitly parked, not half-finished by
  accident — don't "complete" it without checking with Jerry first.
- ScriptForge used to live here (orphaned, unwired) before its 2026-09-05 move to
  `sector2/apps/scriptforge/` — no leftover ScriptForge files remain here; if you find any,
  that's new drift, not the original state.
