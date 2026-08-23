# Phoenix Session State
# Updated: 2026-08-23
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

1. **Glossary dashboard UI panel** — next up, backend/API already confirmed
   working (see docs/GLOSSARY.md). Build the panel now.
2. Write SHARED-FS-TEST.md — detailed instructions doc for this test
   (Jerry requested, covers full setup + both distros + troubleshooting)
3. Make SMB mount automatic on boot — update fstab/credentials in running VM
   (current VM needs manual mount; new boots use updated seed automatically)
4. MapTiler map panel in dashboard
5. Shade UI + drawer filesystem
6. Deploy phoenix-dashboard.service on Ubuntu 192.168.1.133
7. Start manual/phoenix_manual.md

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
