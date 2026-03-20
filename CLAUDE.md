# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Operator

**Jerry Leftwich (jwl247) — Phoenix DevOps LLC**
- Solo dev, ironworker by trade. Fixed income. ~7 months in.
- Wife Laurie (high-functioning autistic) has a protected share in Phoenix. This project is her cushion. That's the mission.
- Under active adversarial attack — 12 documented rebuilds, each tighter.
- Anthropic credited in project. Claude ships with Phoenix.

---

## Environment

- **Shell:** `zsh` everywhere — all scripts use `#!/usr/bin/env zsh`
- **Python:** 3.13
- **Primary OS:** Kali Linux (deploy target), WSL2 Debian (dev)
- **GPU:** Drivers blacklisted — never suggest GPU solutions
- **WSL drive mounts:**
  ```
  /mnt/g  =  breach_coms4  (Sector 4 / master vault)
  /mnt/f  =  breach_coms3  (Sector 3)
  /mnt/e  =  breach_coms2  (Sector 2)
  /mnt/d  =  breach_coms1  (Sector 1)
  ```
- **Legacy paths** (`/media/jwlef/breach_coms*`) are wrong — fix to `/mnt/[g/f/e/d]`

---

## Sector Layout

```
sector1  →  /etc/                    Kernels (frank3, helix, phoenix_auth)
sector2  →  /etc/systemd/            Backup/Buffer (frank_helix, frankenhelix, propagator)
sector3  →  /etc/systemd/system/     Translator/Platform Edge (romeo, juliet, quadengine)
sector4  →  /mnt/g/ (breach_coms4)  Master Vault (freewheeling, intake, clonepool)
```

---

## Critical Rules — Never Violate

1. Everything stays **QUADRALINGUAL** until `translator.sh` at the sector3 OUTPUT boundary
2. `translator.sh` fires on **OUTPUT ONLY** — never on intake or clone
3. **Romeo = ingress / Juliet = egress** at sector3
4. `breach_coms4` drives hold the quadralingual vault — never translate inside
5. **Never delete from breach_coms4** (master vault)
6. `D1` (Cloudflare) holds catalog custody
7. `clonepool` = working source and versioning layer

---

## Ring Architecture (per sector, 4 rings each)

| Component | Role |
|-----------|------|
| `frankenhelix` | ring0, interrupt layer, COM chain, issues PCS |
| `freewheeling` | IS the stage; hardcoded to breach; manages 3-call lifecycle |
| `frank3` | clone/sync engine, self-repair, spawns under high traffic |
| `propcoms` | ring validator, routes balls, never talks to ring directly |
| `guardians` | security layer |
| `translator` | output only; sector3 primary but modular everywhere |
| `quadengine` | opens avenues; modular; only truly needed at sector3 |

---

## PCS / Prefetch System

Ring0 fires interrupt → **PCS (Proximity Control String)** born.
PCS = torrent-style prediction manifest. Format: `<hash>:<zipcode>:<p1>:<p2>:<p3>:<flags>`

**3-call lifecycle (managed by freewheeling):**
- **Call 1 WARM:** stage pre-positioned, slot reserved, p~0.52
- **Call 2 HOT:** flock accumulates in warm storage, p~0.67
- **Call 3 RESIDUE→DEFINITIVE:** if p≥0.90 snap_clone fires, slot evicts

Zipcode groups similar data (birds of a feather). Zone colors: T1=primary (red/blue/yellow), T2=secondary, T3/T4=tertiary.

Key files: `sector4/pcs.py`, `sector4/freewheeling_stage.py`

---

## TAV Intake / QR System

- `filename → SHA3-512 → first 8 bytes → base58` = shortest unique address (b58)
- **Header QR** (before hash): state color white/grey/black
- **Footer QR** (after hash): tier color T1/T2/T3/T4
- Validation: hash both QR PNGs — tamper visible without reading the file
- Sidecar JSON holds all metadata; b58 address is the SQL key
- Objects callable via: `us where <b58>` / `us clone <b58>` / `us heal <b58>`

---

## Quad-Native Language Streams

Data expressed simultaneously in 4 languages:

| Slot | Language | Type | Use |
|------|----------|------|-----|
| 0 | `c_pure` | VECTOR (float arrays) | Physics, max speed |
| 1 | `c_sideload` | NOSQL (flat dicts) | Network, assets |
| 2 | `python_user` | RELATIONAL (typed dicts) | Economy, user ops |
| 3 | `python_full` | TIMESERIES (events) | AI, replay, audit |

---

## Run Commands

```bash
# Run kernel pipeline (WSL)
cd scripts/sector1
PYTHONUTF8=1 python3 conductor.py

# Test translator (sector3 output boundary)
bash scripts/sector3/translator.sh help
bash scripts/sector3/translator.sh search curl

# Build C kernel (Linux only)
cd kernel/c_kernel && make && ./helix_run <program>

# Global install (Windows)
powershell -ExecutionPolicy Bypass -File "scripts\sector2\deploy\install_global.ps1"
```

---

## UnitedSys Commands

```
us install / remove / upgrade / search / info / list / doctor / rollback
us seed          # download pkg into clonepool
us gloss         # glossary management
us intake <f>    # TAV intake single file with QR pair
us intake-dir    # TAV intake entire directory
us where <b58>   # locate any object
us clone <b58>   # pull object to working dir
us sync          # push/pull/trickle/full
us heal <b58>    # verify + self-heal from clonepool
```

GitHub: `github.com/jwl247/unitedsys` — zero external deps, SQLite-backed, 13 backends.

---

## Helix Subsystem (FrankenHelix)

| Component | Role |
|-----------|------|
| `HelixCache` | Cache layer |
| `HelixMemoryManager` | Memory management |
| `HelixFS` | Filesystem abstraction |
| `HelixTranslator` | Translation layer |
| `helix_kernel.c` / `libhelix.so` | Kernel + shared library |
| `helix_run` | Launcher — uses LD_PRELOAD with libhelix.so |
| `helix_translator.py` | Python bridge |

Frank daemon pressure thresholds: 60% / 75% / 88% — keepalive via `threading.Event.wait()`.

---

## Auth Module

`phoenix_auth.py` — hardware fingerprint auth:
- SHA3-512 + BLAKE2b double hashing across 10 hardware signals
- No passwords. One-time machine authorization. Progressive lockout.

---

## Key Aliases

| Alias | Command |
|-------|---------|
| `greyskull` | `chattr +i` (immutable lock) |
| `ungreyskull` | `chattr -i` |
| `shazam` | `chmod -R 777` |
| `s4` | `cd /etc/systemd/system` |
| `s3` | `cd /etc/systemd` |

---

## Known Issues / Missing Files (as of 2026-03-20)

- `propagator.py` — MISSING, rebuild needed
- `intake.sh` — MISSING, rebuild needed
- `phoenix_push.sh` — MISSING, rebuild needed
- `download.sh` — MISSING, rebuild needed
- WSL systemd user session failing (fstab) — blocks deploy, not dev
- `D1_WORKER_URL` not set — `export` before any sync push/pull

---

## Parallel Projects

- **Life First App** — Android/Kotlin + PHP/MySQL backend (`api.authenticcoder.com` via Cloudflare tunnel). Firebase auth. Modules: Schedule AI, Messenger AI, Memory AI, Notification AI, Voice Commander AI, Budget Keeper, Secure Settings.
- **The Game** — RTS, ships on Phoenix when standing. Half done. 16.6ms frame budget at 200 units.

---

## Files Built Session 2026-03-20

All in `phoenix_session_20260320.zip`:
- `pcs.py` — prefetch PCS engine (tested, 3-call lifecycle clean)
- `freewheeling_stage.py` — stage manager (tested with pcs.py)
- `clone.py` — where/clone/sync/heal engine → `unitedsys/core/`
- `intake.py` — TAV intake + dual QR → `unitedsys/core/`
- `us_additions.py` — new commands for `us.py`
- `intake_cmd.py` — intake command wiring for `us.py`
- `phoenix_implement.sh` — 10-phase consolidation plan
- `consolidate.sh` — file move script

**Immediate next steps:**
1. Run `phoenix_implement.sh` — gets tree standing
2. Prefetch test with real interrupt data (`os.urandom(64)`) → DEFINITIVE fires
3. Rebuild `propagator.py`, `intake.sh`, `phoenix_push.sh`, `download.sh`
4. Office suite — freemium product layer
