# construct.md — Phoenix DevOps OS Build Reference
# jwl247 / Jerry Leftwich / Phoenix DevOps LLC
# ABSOLUTE REFERENCE for Grok Build mode. One file at a time. Backup first (oldarch).
# =============================================================================

## WHO / WHAT
Phoenix DevOps OS — deterministic, agnostic, prefetched, self-healing, versioned OS.
Windows build path: PowerShell 7 + Git Bash. Linux path: bash/zsh + systemd.
License: GPL v3. Real code only. No demos.

## REPO PATHS
| Path | Role |
|------|------|
| `C:\Phoenix-DevOps-oS` | Canonical workspace (full four-sector tree) |
| `$HOME\Phoenix\Phoenix-DevOps-oS` | Installed OS repo location (install.ps1 target) |
| `$HOME\Phoenix\package-handler` | Sector 2 intake engine (until migrated into sector2/) |
| `archive/oldarch.json` | Catch-all backup manifest — update before every overwrite |

## DESIGN RULES (every generated file)
1. PowerShell 7 first (Windows focus)
2. Heavy comments — new contributors must understand intent
3. Security-first — minimal local surface, user scope, no unnecessary elevation
4. No unnecessary dependencies
5. Forward-compatible with Desktop Phase 2

## BUILD ORDER

### Phase 0: Repo Cleanup
- [x] Confirm repo root (`C:\Phoenix-DevOps-oS` or installed copy)
- [x] Run `git status`
- [ ] Clean `website/` submodule (deferred — loose git internals at root; see oldarch)
- [x] Backup to `archive/` + update `archive/oldarch.json`

### Phase 1: Core Global Command Layer
- [x] **Task 1:** `scripts/usys.ps1` — module + shim, magic `.lol`/`.phx`, PATH register
- [x] **Task 2:** `install.ps1` — installs usys, PATH, file associations, optional Cloudflare tunnel
- [x] **Task 3:** `scripts/intake.ps1` — modernized intake wrapper (Sector 2 pipeline)

### Phase 2: Desktop Environment (next big leap)
- [ ] Lightweight GUI shell (`desktop/` spec)
- [ ] File Manager with clonepool integration
- [ ] Terminal (usys-aware)
- [ ] App Store / Package GUI
- [ ] Settings app

### Phase 3: Gaming Layer
- [ ] TBD — spec after Phase 2 shell stands

## PHASE 1 FILE MAP
```
Phoenix-DevOps-oS/
├── construct.md          ← this file
├── install.ps1           ← Windows one-liner installer
├── scripts/
│   ├── usys.ps1          ← global command layer (DONE)
│   ├── usys.cmd          ← PATH shim → pwsh
│   └── intake.ps1        ← intake wrapper
├── tools/
│   ├── clone.ps1         ← legacy; usys clone delegates here
│   └── clone.sh
└── archive/
    └── oldarch.json      ← backup manifest
```

## USYS COMMANDS (scripts/usys.ps1)
| Command | Sector | Purpose |
|---------|--------|---------|
| `usys init` | — | First-time setup |
| `usys status` | all | Repo + engine health |
| `usys intake` | 4 | Vault TAV intake |
| `usys clone` | 2 | Clonepool intake |
| `usys search` | 2 | Clonepool + catalog search |
| `usys open` | 2/4 | Magic `.lol` / `.phx` handler |
| `usys register/call/...` | — | UnitedSys registry (bash delegate) |

## INSTALL ONE-LINER (after Task 2)
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

## GROK BUILD PROTOCOL
For each file:
1. Backup affected paths → `archive/<timestamp>/` + update `oldarch.json`
2. Generate full file content
3. Provide copy/install commands
4. Provide testing steps
5. Suggest commit message
6. Mark checkbox in this file

## SESSION LOG
| Date | Item | Status |
|------|------|--------|
| 2026-06-07 | Phase 0 backup + usys.ps1 | done |
| 2026-06-07 | construct.md + install.ps1 + intake.ps1 + usys.cmd | done |