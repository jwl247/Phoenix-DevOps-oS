# PHOENIX DEVOPS OS — Claude Code Persistent Context
# jwl247 / Phoenix DevOps LLC
# Generated: March 2026
# Status: ACTIVE — post-consolidation canonical state
#
# READ THIS FIRST EVERY SESSION.
# Run ~/projects/phoenix-devops/status.sh before touching anything.
# =============================================================================

## IDENTITY
Project  : Phoenix DevOps OS (Phoenix-DevOps-oS)
Author   : jwl247 / Jerry Leftwich / Phoenix DevOps LLC
License  : GPL-3.0
GitHub   : jwl247/phoenix-devops    ← primary (CREATE THIS REPO)
           jwl247/unitedsys         ← standalone package handler
Shell    : zsh (ALL scripts: #!/usr/bin/env zsh)
Env      : WSL2 Debian → deploy target: Kali/RHEL
Python   : 3.13 (venv active at ~/projects/phoenix-devops/.venv)
Prompt   : (.venv) phoenix%

## THE MISSION
Build the infrastructure that makes everything else possible.
UnitedSys = global clone and sync backbone.
Phoenix = quad-native OS framework.
The game ships on top of this when it's standing.

## ARCHITECTURE — FOUR SECTORS
```
sector1  →  /etc/                    Kernels
sector2  →  /etc/systemd/            Backup / Buffer
sector3  →  /etc/systemd/system/     Translator / Platform Edge
sector4  →  /mnt/g/                  Master Vault (breach_coms4)
```
Project tree lives at ~/projects/phoenix-devops/
Deploy script promotes into /etc/ with sudo at deploy time only.
Nothing needs sudo during development.

## CRITICAL RULES — READ EVERY SESSION
1. Everything stays QUADRALINGUAL until translator.sh at sector3 boundary
2. translator.sh fires on OUTPUT ONLY — never on intake or clone
3. Romeo handles ingress / Juliet handles egress at sector3
4. breach_coms drives hold quadralingual vault — never translate inside them
5. All scripts target zsh — shebangs must be #!/usr/bin/env zsh
6. GPU drivers blacklisted — never suggest GPU-dependent solutions
7. WSL breach_coms paths: /mnt/[g|f|e|d]/ NOT /media/jwlef/breach_coms[1-4]
8. D1 holds catalog custody — clonepool is working source
9. Header QR before hashing / Footer QR after hashing — never swap
10. Never delete from breach_coms4 (master vault)

## BREACH_COMS DRIVE MAP (WSL)
```
breach_coms4  →  /mnt/g   T1 PRIMARY colors    master vault, intake writes here
breach_coms3  →  /mnt/f   T2 SECONDARY colors  day-1 mirror
breach_coms2  →  /mnt/e   T3 TERTIARY colors   day-2 mirror
breach_coms1  →  /mnt/d   T4 TERTIARY colors   day-3 mirror, 4-day window
clonepool     →  /mnt/d/clonepool              callable face of the vault
```
Override via env vars: BREACH_COMS4, BREACH_COMS3, BREACH_COMS2, BREACH_COMS1, CLONEPOOL

## PROJECT TREE — CANONICAL
```
~/projects/
├── phoenix-devops/          ← main repo (jwl247/phoenix-devops)
│   ├── CLAUDE.md            ← this file
│   ├── README.md
│   ├── install.sh
│   ├── status.sh            ← run this first every session
│   ├── saddle_block.sh
│   ├── align_dirs.sh
│   ├── sector1/             ← /etc/ — kernels
│   │   ├── kernels/         frank3_slot_a.c, frank3_slot_b.c, Makefile
│   │   ├── helix/           helix stack (kernel, run, conf, c_express)
│   │   ├── auth/            phoenix_auth.py
│   │   └── concierge/       concierge.c, bridge.py, linux_concierge.py
│   ├── sector2/             ← /etc/systemd/ — backup/buffer
│   │   ├── frank/           frank_helix.py, frank_save.py, frank_http.py, frank_client.js
│   │   ├── ring0/           frankenhelix.py
│   │   └── propagator/      propagator.py (REBUILD), dispatch.json, propcoms.sh
│   ├── sector3/             ← /etc/systemd/system/ — platform edge
│   │   ├── translator/      translator.sh
│   │   ├── romeo_juliet/    romeo.py, juliet.py, dbl_juliet.py
│   │   ├── quadengine/      quadengine.py
│   │   └── services/        all .service and .target files + install-units.sh
│   ├── sector4/             ← breach_coms4 (/mnt/g/)
│   │   ├── intake/          intake.sh (REBUILD)
│   │   └── vault/           phoenix_push.sh (REBUILD), download.sh (REBUILD)
│   ├── deploy/              deploy.sh, windows/build_windows.bat, windows/start_wsl.sh
│   ├── tools/               align_dirs.sh, get_distros.sh, benchmarks/
│   ├── docs/                README per sector, systemd/, config/
│   └── unitedsys/           ← git submodule → jwl247/unitedsys
└── unitedsys/               ← standalone repo root (jwl247/unitedsys)
    ├── bin/us               zsh shim
    ├── core/                us.py, catalog.py, clone.py, intake.py, glossary.py...
    ├── db/schema.sql
    ├── manifests/
    └── docs/
```

## COMPONENT STATUS
```
EXISTS + CORRECT
  frank3_slot_a.c          ~/projects/phoenix/frank3_slot_a.c       → move to sector1/kernels/
  frank3_slot_b.c          ~/projects/phoenix/frank3_slot_b.c       → move to sector1/kernels/
  frank3-slot-a.service    ~/projects/phoenix/frank3-slot-a.service → move to sector3/services/
  frank3-slot-b.service    ~/projects/phoenix/frank3-slot-b.service → move to sector3/services/
  Makefile                 ~/projects/phoenix/Makefile              → move to sector1/kernels/
  install.sh               ~/projects/phoenix/install.sh            → move to root
  saddle_block.sh          ~/projects/phoenix/saddle_block.sh       → move to sector1/
  unitedsys/               ~/projects/phoenix/unitedsys/            → move to ~/projects/unitedsys/

IN DOWNLOADS — needs moving
  frank_helix.py           → sector2/frank/
  frankenhelix.py          → sector2/ring0/
  frank_http.py            → sector2/frank/
  frank_save.py            → sector2/frank/
  helix_complete_stack.py  → sector1/helix/
  helix_complete_package.py→ sector1/helix/
  helix_slim.py            → sector1/helix/
  helix_translator.py      → sector1/helix/
  helix_vram.py            → sector1/helix/
  align_dirs.sh            → tools/
  get_distros.sh           → tools/
  install-units.sh         → sector3/services/
  start_admin.sh           → unitedsys/ root
  glossary_api.py          → unitedsys/ root

IN ZIPS — needs extracting (see consolidate.sh)
  romeo.py, juliet.py, dbl_juliet.py   → sector3/romeo_juliet/  (romeo_juliet.zip)
  phoenix_auth.py                       → sector1/auth/          (PhoenixDevOps_sector1.zip)
  quadengine.py                         → sector3/quadengine/    (PhoenixDevOps_sector1.zip)
  helix kernel files                    → sector1/helix/kernel/  (files(8).zip)
  frankenhelix.py (zip ver)             → sector2/ring0/         (PhoenixDevOps_sector2.zip)
  dispatch.json                         → sector2/propagator/    (PhoenixDevOps_sector2.zip)
  deploy.sh                             → deploy/                (PhoenixDevOps_sector2.zip)
  12 systemd units                      → sector3/services/      (files(11).zip)
  READMEs (newest 2026-03-19)           → docs/                  (files(12).zip)
  translator.sh                         → sector3/translator/    (sector2_extract folder)

BUILT THIS SESSION — needs placing
  core/clone.py            → ~/projects/unitedsys/core/clone.py
  core/intake.py           → ~/projects/unitedsys/core/intake.py
  (us_additions.py)        → wire into ~/projects/unitedsys/core/us.py
  (intake_cmd.py)          → wire into ~/projects/unitedsys/core/us.py

MISSING — rebuild after tree is correct
  propagator.py            → sector2/propagator/
  intake.sh                → sector4/intake/
  phoenix_push.sh          → sector4/vault/
  download.sh              → sector4/vault/
```

## UNITEDSYS COMMANDS (current)
```
us install <pkg>           install via detected backend
us remove <pkg>            remove package
us upgrade [pkg]           upgrade package or all
us search <query>          search available packages
us info <pkg>              show package details
us list                    list installed (catalog)
us doctor                  diagnose system + backends
us rollback                undo last transaction
us seed <pkg>              download pkg into clonepool
us gloss list/info/amend   glossary management
us intake <file>           TAV intake single file with QR pair  ← NEW
us intake-dir <dir>        TAV intake entire directory          ← UPDATED
us where <name>            locate any object                    ← NEW
us clone <name> [--to]     pull object to working dir           ← NEW
us sync [push|pull|trickle|full]  sync catalog + trickle       ← NEW
us heal <name>             verify + self-heal from clonepool    ← NEW
```

## TAV ADDRESS SYSTEM
```
filename → SHA3-512 → first 8 bytes → base58 = shortest unique address
Example: frank_helix.py → a3f9c2b1d7e84f12 → 3vKmRp4x

Header QR (before hash):  USYS:<b58>:HEADER  — state color (white/grey/black)
Footer QR (after hash):   USYS:<b58>:FOOTER:<sha3_fp>:<b2_fp>  — tier color

Tier colors:
  T1 = primary   (red/blue/yellow)    breach_coms4
  T2 = secondary (orange/green/purple) breach_coms3
  T3 = tertiary  (teal/brown/olive)   breach_coms2
  T4 = tertiary  (slate/mauve/sage)   breach_coms1

Validation: hash both QR PNGs — if tampered, SHA3 won't match sidecar
```

## KNOWN ISSUES
- WSL systemd user session failing on startup (/etc/fstab mount -a failed)
  → Fix: sudo nano /etc/fstab, comment out missing drives, sudo mount -a
  → Blocks sector deployment but NOT development
- All legacy code has /media/jwlef/breach_coms paths → need /mnt/[g/f/e/d]
  → Fix: sed -i 's|/media/jwlef/breach_coms4|/mnt/g|g' on all .py and .sh
- D1_WORKER_URL not set → sync push/pull will warn but not fail
  → Fix: export D1_WORKER_URL=https://your-worker.workers.dev
- propagator.py missing → D1 sync falls back to direct HTTP (handled)

## SESSION STARTUP CHECKLIST
Run this before every session:
  ~/projects/phoenix-devops/status.sh

It checks:
  1. Sector folder structure
  2. breach_coms mounts (/mnt/g/f/e/d)
  3. systemd user session health
  4. UnitedSys functional (us list)
  5. Git remote status
  6. Catalog entry count

## GIT REMOTES
  jwl247/unitedsys     → git@github.com:jwl247/unitedsys.git     EXISTS
  jwl247/phoenix-devops → git@github.com:jwl247/phoenix-devops.git  CREATE THIS

## OVERLAP STRATEGY
  unitedsys lives at ~/projects/unitedsys/ (own repo, own git)
  phoenix-devops references it as git submodule at phoenix-devops/unitedsys/
  lifefirst will also reference it as submodule when that project activates

## THE GAME
Ships on top of this stack when Phoenix is standing.
Half done. Don't forget.

## ANTHROPIC / CLAUDE
Claude is the designated AI collaborator on this project.
Anthropic receives credited acknowledgment in the project.
Claude Code uses this file as persistent context every session.
=============================================================================
