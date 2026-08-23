# Phoenix Session State
# Updated: 2026-08-24
# READ THIS AT THE START OF NEXT SESSION

## WHERE WE ARE

Dashboard is real end to end. Clonepool integrity system is real end to end.
Shared filesystem is real end to end — proven live 2026-08-23.

- Dashboard Electron app — real D1/R2 data, PS7 shell, clonepool browser,
  screenshot analysis, live monitor, dedicated Claude "subscription" mode ✅
- R2 actually receiving bytes ✅
- Content-hash integrity system (SHA3-512 + BLAKE2b baseline) ✅
- QR generation (header/footer) live in the active bash intake.sh pipeline ✅
- PHOENIX_AUTH rotated and working ✅
- Whole repo intaked — 376 files ✅
- Debian running via QEMU — booted, SSH confirmed, phoenix user created ✅
- Windows ↔ Debian shared filesystem PROVEN LIVE ✅
  - Windows wrote test.txt → Debian read it
  - Debian wrote from-debian.txt → Windows read it
  - F:\Phoenix\ hosted on Windows, mounted at /phoenix inside Debian
  - Bridge: SMB over QEMU user-net (10.0.2.2), credentials file
  - No WSL. No virtfs. No Hyper-V. No install. Phoenix brought the OS.
- Double Helix PoC wired end-to-end ✅
  - Helix Lightning Kernel confirmed in sector1/helix-lightning/ (cpython-314 present)
  - true_double_helix.py: path-fixed, snapshot writer added
  - helix_suit_override.py: parents index fixed (parents[1]→parents[2])
  - paging.py: attach_helix() + attach_snapshot_path() + _read_snapshot_json() wired
  - Launchers: run-helix-poc.ps1 (Windows) + run-helix-poc.sh (Debian)
  - Suite registered: helix-poc.suite.json
  - Plan: tools/poc/DOUBLE-HELIX-PLAN.md

## WHAT WAS BUILT THIS SESSION (2026-08-24)

### Double Helix PoC — kernel wired end-to-end

- `tools/poc/true_double_helix.py` — path fix (sys.path insert for sector1/helix-lightning/),
  snapshot writer added: `attach_helix_system()`, `_snapshot_writer_loop()`, `page_dir` param.
  Writes `windows_snapshot.json` atomically every 5s to `PHOENIX_HELIX_PAGE_DIR`.
- `sector1/helix-lightning/helix_suit_override.py` — `parents[1]` → `parents[2]` fix.
  Was always pointing at sector1/ (wrong). Now points at repo root. helix_complete_stack.py
  wires as suit for all 13 core rings correctly when PHOENIX_SUITS is not set.
- `sector4/paging.py` — `attach_helix()`, `attach_snapshot_path()`, `_read_snapshot_json()`,
  3-tier snapshot priority, `helix_paging` signal in monitor loop, shrink gated on
  `not helix_paging`, `_log_helix_status()`, `helix_source` in status dict, auto-reads
  `PHOENIX_PAGING_SNAPSHOT_PATH` env var at start.
- `tools/poc/run-helix-poc.ps1` — Windows launcher. Sets PHOENIX_SUITS, PHOENIX_HELIX_PAGE_DIR,
  PYTHONPATH. Creates F:\Phoenix\helix-pages\. Runs py -3 true_double_helix.py.
- `tools/poc/run-helix-poc.sh` — Debian launcher. Verifies SMB mount. Sets env. Runs
  paging.py start with snapshot path. Re-execs with sudo if not root.
- `tools/poc/helix-poc.suite.json` — suite registration. usys run helix-poc.
- `tools/poc/DOUBLE-HELIX-PLAN.md` — plan file (renamed from HELIX-DOUBLE-STRAND-PLAN.md).
- `tools/poc/install-helix-autostart.ps1` — Windows autostart installer. Method A: Task
  Scheduler (run as Admin once). Method B: Startup folder fallback (zero elevation, installed).
  Startup shortcut confirmed: `%APPDATA%\...\Startup\Phoenix-HelixLightningKernel.cmd`
- `sector3/services/phoenix-helix-kernel.service` — Debian systemd service for paging brain.
  Auto-starts after network + SMB mount. `ExecStartPre` guards on `/phoenix/helix-pages/`.
- `tools/poc/HELIX-LIGHTNING-GUIDE.md` — complete standalone guide: architecture, running,
  persistence, troubleshooting, environment variables, ports, connections to all sectors.

## WHAT WAS BUILT THIS SESSION (2026-08-23)

### Shared Filesystem — Windows ↔ Debian (PROVEN LIVE)
- `tools/poc/setup-shared-fs.ps1` — one-time bootstrap, creates F:\Phoenix\*
- `scripts/usys.ps1` — PhxSharedRoot, ConvertTo-QemuHostPath, Write-PhxFsBanner,
  phx-import/export/sync/ls wrappers, Test-PhxSharedPath, usys fs-* dispatcher,
  -Share switch on Invoke-UsysRun, auto format=raw/.img detection
- `tools/poc/debian-seed/user-data` — cifs-utils, credentials file, fstab entry
- `tools/poc/ubuntu-seed/user-data` + `meta-data` — NEW, same pattern for Ubuntu
- `tools/poc/debian.suite.json` — entry filename fixed, shared_fs metadata
- `tools/poc/ubuntu.suite.json` — shared_fs metadata, login corrected to phoenix
- `tools/poc/README.md` — full shared filesystem section

### Key discoveries
- QEMU on Windows (both official installer and MSYS2 mingw64) ships with
  virtfs DISABLED — compile-time flag, WinFsp does not fix it
- SMB over QEMU user-net (10.0.2.2) is the working bridge — same result,
  no virtfs needed, works on every QEMU build
- Windows guest SMB auth is blocked by default since Win10 1709 — requires
  real credentials even for Everyone shares
- PS7 is required — PS5.1 intercepts `ssh -p` as Get-Process parameter

## KNOWN LOOSE ENDS (not urgent, not forgotten)

- `dashboardDEP/` and other `*DEP`-suffixed dirs share filenames with live
  counterparts — intake.sh's hex_id is filename-only, so both land under
  the same hex bucket as separate versions rather than colliding
  destructively, but it's confusing. Consider excluding `*DEP` dirs from
  intake or renaming them off the collision path.
- Tonight's whole-repo intake was run as `intake .`, so its directory-level
  summary entry got hex `2e` / name `.` instead of `Phoenix-DevOps-oS`.
  Cosmetic only — every individual file underneath is correctly named.
- The integrity-verification gate only covers `intake clone` (both
  single-file and directory-snapshot forms) so far. `intake_file`'s own
  duplicate-detection path and true hot-swap don't check hashes yet.
- HUD visual translucency — scoped to visual-only, not yet implemented.
- 3 redundant PS7 buttons in the dashboard UI — not yet consolidated.

## NEXT STEPS IN ORDER

1. **Run Debian paging brain** — SSH into Debian, run `run-helix-poc.sh`.
   Verify `[SNAPSHOT]` tier lines appear in paging.py logs.
   Windows snapshot confirmed writing ✅ (timestamp fresh, all fields present).
   Windows autostart confirmed installed ✅ (Startup folder .cmd).
2. **Deploy Debian systemd service** — copy `phoenix-helix-kernel.service` to
   `/etc/systemd/system/`, enable + start. Requires SMB fstab entry for auto-mount.
3. **Glossary dashboard UI panel** — backend/API already confirmed working.
4. Write SHARED-FS-TEST.md — detailed setup + troubleshooting doc.
5. Make SMB mount automatic on boot.
6. MapTiler map panel in dashboard.
7. Shade UI + drawer filesystem.
8. Deploy phoenix-dashboard.service on Ubuntu 192.168.1.133.
9. Start manual/phoenix_manual.md.

## KEY FILES

| File | Purpose |
|------|---------|
| `CLAUDE.md` (repo root) | Full architecture reference + session log — read this first |
| `sector2/package-handler/intake.sh` | Intake pipeline — hex identity, hashing, QR, R2, D1, integrity gate |
| `sector2/package-handler/README.md` | Command reference + integrity verification docs |
| `sector3/workers/packages-worker/index.js` | Cloudflare Worker — D1 + R2 API |
| `scripts/usys.ps1` | Global command layer (PowerShell) |
| `dashboard/main.js` | Electron main process — D1/R2/Claude/Ollama wiring |

## WHY THIS EXISTS
Life First app for Laurie. Local LLM, no vendor, no subscription, no lock-in.
Phoenix is the infrastructure. Every process, every import, every run is in service of that.
People with less money deserve to run the same tools as everyone else.
Every penny every time.
