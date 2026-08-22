---
imported: 2026-03-12
source: Disk 3 — Seagate BUP Slim 2TB (Kali Linux, ext4)
---

# Kali Import Notes

## What came over clean
- `phoenix/` — full project, all scripts, sector4 source, DB schema, usys.sh
- `dblhelix.py`, `dblhelix1.py`, `franken2.py` — Python source from home dir
- `README_sector4.md`, `UNITEDSYS_README.md`
- `RECOVERED/`, `RECOVERED2/` — recovered file sets from Kali

## What needs to be repulled
- `phoenix/SECTOR4-coms` — symlink on Kali filesystem resolved to drive root (corrupted pointer)
  - **Reason:** ext4 symlinks don't transfer cleanly to NTFS via WSL mount
  - **Fix:** repull from source repo or rebuild from sector4/coms1-4 directories
- `phoenix/SECTOR4` (uppercase) — verify contents match sector4/ (lowercase) source

## What was left behind (not needed)
- balenaEtcher binaries
- Steam/Flatpak installers
- Ventoy installer archives (have newer version)
- `.git` objects (permission-denied on NTFS, git history not migrated — reinit on Windows)

## Mount method used
- `wsl --mount \\.\PHYSICALDRIVE3 --partition 1 --type ext4` (WSL2 disk attach)
- Mount goes stale across WSL sessions — files copied via `/dev/sdd1` mount inside Debian
- Destination: `C:\Users\jwlef\PhoenixDevOps\_kali_import\`
