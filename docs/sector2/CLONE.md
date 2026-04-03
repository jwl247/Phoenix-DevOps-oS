# Clone -- Sector 2 Intake Command
**USys -- United Systems | jwl247**
**Sector:** 2 -- Intake / Package Handler
**Status:** Active

---

## What It Is

`clone` is the universal intake command for the Phoenix system.
Single point of entry for any file, package, config, or script
entering Phoenix -- from any shell, on any platform.

One command. Every platform. Everything tracked.

---

## Files

| File | Repo | Purpose |
|------|------|---------|
| `tools/clone.ps1` | Phoenix-DevOps-oS | PS7 global function |
| `tools/clone.sh` | Phoenix-DevOps-oS | Bash shim -- Linux/WSL/macOS |
| `intake/intake.sh` | Phoenix-Package_handler | Intake engine (what clone wraps) |
| `worker/index.js` | Phoenix-Package_handler | packages-worker -- D1 sync |

---

## Install

### PowerShell 7 (Windows)

Add one line to your PS7 profile (`$PROFILE`):

```powershell
. "$HOME\Phoenix\Phoenix-DevOps-oS\tools\clone.ps1"
```

Reload: `. $PROFILE` -- then `clone` works from anywhere in PS7.

### Bash -- Linux / WSL / macOS

```bash
chmod +x ~/Phoenix/Phoenix-DevOps-oS/tools/clone.sh
sudo ln -s ~/Phoenix/Phoenix-DevOps-oS/tools/clone.sh /usr/local/bin/clone
```

---

## Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PHOENIX_AUTH` | Yes (for D1) | -- | packages-worker auth token |
| `PHOENIX_WORKER_URL` | Yes (for D1) | -- | packages-worker URL |
| `CLONEPOOL_DIR` | No | `~/Phoenix/clonepool` | Local clonepool path |
| `PHOENIX_INTAKE` | No | auto-detected | Override path to intake.sh |

---

## Usage

### PowerShell 7

```powershell
clone ./franken.py
clone ./nginx.conf -Tag "production config" -Category configs
clone ./franken.py -Destination T2
clone ./myfile.sh -DryRun
```

### Bash / WSL / Linux / macOS

```bash
clone ./franken.py
clone ./nginx.conf configs "production nginx"
clone backend nodejs winget 20.11.0
clone --dry-run ./myfile.sh
clone status
```

---

## What Happens When You Clone

```
clone ./franken.py
        |
  clone.ps1 / clone.sh  (shim -- finds intake.sh, handles paths)
        |
  intake.sh  (Phoenix-Package_handler/intake/)
        |
  hex identity generated from filename
  sidecar.json written
  clonepool versioned (v1, v2, v3...)
  custody receipt -- local sqlite3 (immutable)
  D1 sync -> packages-worker -> phoenix-catalog
        |
  File cataloged. Custody locked.
```

---

## Sector Map

Clone is a **Sector 2** operation with **Sector 1** authority (PCS embedded).
By the time clone finishes, Sector 3 already knows the pattern.
Sector 4 will prefetch it on next access.

---

## Test It

```bash
# Dry run first -- no writes
clone --dry-run ./anyfile.txt

# Real clone
clone ./anyfile.txt

# Check status
clone status
```

---

## QR State After Clone

| QR | State | Meaning |
|----|-------|---------|
| Top -- White | Active | File is good, current |
| Top -- Grey | Deprecated | Older version, superseded |
| Top -- Black | Compromised | Do not use |
| Bottom | Location | T1/T2/T3/T4 -- max 4 deep |

---

*Built by JW -- Phoenix DevOps OS | USys -- United Systems | GPL-3.0*
