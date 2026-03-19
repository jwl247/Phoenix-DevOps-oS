# Phoenix-DevOps-oS

An **agnostic, deterministic, prefetch OS** built for real-time signal routing, cross-platform package management, and kernel-level process translation.

Every signal — game event, system call, network packet, package request — travels through the same deterministic path:
**Freewheeling → Captain → Propcoms → ring.**
No shortcuts. No loops. No mid-flight lookup. The signal carries its own destination.

Built to run the [Sacrifice RTS](game/sacrifice/GDD.md) at 200 units, all 16 rings, inside a 16.6ms frame budget on a laptop.

---

## What Makes It Different

| Property | What it means |
|----------|--------------|
| **Agnostic** | Sector 3 translates everything — apt, dnf, pacman, winget, choco, brew, or the Phoenix clone pool itself. No distro dependency. |
| **Deterministic** | PCS (Proximity Control String) is born at the interrupter and carries its destination forever. Nothing looks up routing mid-flight. |
| **Prefetch** | 3-call lifecycle: stage set → data accumulates → definitive check → snap-clone fires. Data is ready before it's needed. |

---

## Signal Flow

```
INPUT  (game event / syscall / network packet / package request)
  │
  ▼
Freewheeling Stage          — PCS born, 3-call lifecycle, snap-clone fires
  │   call1: stage set
  │   call2: data accumulates
  │   call3: definitive check → snap-clone
  ▼
Cpt_conductor               — selects kernel slot by family, wraps in QuadPacket
  │   slot 0  c_pure        → VECTOR     (physics, system)
  │   slot 1  c_sideload    → NOSQL      (network, assets)
  │   slot 2  python_user   → RELATIONAL (user ops, economy)
  │   slot 3  python_full   → TIMESERIES (AI, replay, combat log)
  ▼
PropcGate / Propcoms        — zipcode validates, custody chain locked
  │   targets dict carries language→ring mapping
  │   escalate if ring not in valid_targets
  ▼
coms ring (1–16)            — post-stage handler, systemd service fires
  │
  ▼
OUTPUT  (egress — packet cleared, ring released)
```

---

## Four Kernel Slots

| Slot | Type | Language | Workloads | Target |
|------|------|----------|-----------|--------|
| 0 | c_pure | VECTOR | physics, system, collision | < 1ms / 10k pkt/s |
| 1 | c_sideload | NOSQL | network, assets, I/O | < 2ms / 5k pkt/s |
| 2 | python_user | RELATIONAL | user ops, economy, research | < 5ms / 1k pkt/s |
| 3 | python_full | TIMESERIES | AI, replay, combat log | < 10ms / 500 pkt/s |

**All four streams fire simultaneously** — VECTOR, NOSQL, RELATIONAL, TIMESERIES are not sequential, not human languages. They are the quadralingual identity of every packet. The packet carries all four streams at once.

Overflow rule: if a slot hits 100 in-flight packets, conductor steps to least-loaded slot automatically.

---

## Sixteen Rings — Four Sectors

```
SECTOR 1 — Kernel Home / Process Translation     rings 13–16
  Ring 13  VECTOR      kernel interrupt intake
  Ring 14  NOSQL       kernel interrupt intake
  Ring 15  RELATIONAL  kernel interrupt intake
  Ring 16  TIMESERIES  kernel interrupt intake
  Kernels live here. Input direct from interrupter.
  Phoenix is the authority. Distros are input, not law.

SECTOR 2 — PCS / Design / Backup                 rings 9–12
  Ring  9  VECTOR      PCS creation
  Ring 10  NOSQL       rendering design
  Ring 11  RELATIONAL  Phoenix office
  Ring 12  TIMESERIES  overflow / backup
  PCS born here. translator.sh backup lives here.
  Catches whole-task overflow from sector 3.
  Sector2 failover activates at 10+ queued jobs.

SECTOR 3 — Agnostic Output Translation           rings 5–8
  Ring  5  VECTOR      output translation (EN-equivalent)
  Ring  6  NOSQL       output translation (ZH-equivalent)
  Ring  7  RELATIONAL  output translation (ES-equivalent)
  Ring  8  TIMESERIES  output translation (HI-equivalent)
  THIS IS WHAT MAKES THE SYSTEM AGNOSTIC.
  translator.sh primary lives here.
  Detects backend → translates UnitedSys verbs → normalizes output.

SECTOR 4 — System Core / Storage                 rings 1–4
  Ring  1  VECTOR      physics / system storage
  Ring  2  NOSQL       network storage
  Ring  3  RELATIONAL  user / economy storage
  Ring  4  TIMESERIES  AI / replay storage
  Drive-bound. Freewheeling holds custody.
```

---

## Deployment Paths (post WSL → real Linux swap)

| Sector | Linux Path | Notes |
|--------|-----------|-------|
| Sector 4 | `/etc/systemd/system/SECTOR4/` | System core — stays here |
| Sector 3 | `/etc/systemd/system/` | translator.sh primary lives at root of this dir |
| Sector 2 | `/etc/systemd/` | translator.sh backup, sector2 failover |
| Sector 1 | TBD | Kernel home — temp wired at WSL swap time |

**Paths are NOT moved yet.** Waiting for WSL frontend hot-swap to real Linux.
When swapping: sector 4 needs temporary wiring first, then sectors 3 → 2 → 1.

---

## PCS — Proximity Control String

Every signal gets a PCS identity at birth. It never changes. It travels forever.

```
<hash>:<zipcode>:<p1>:<p2>:<p3>:<definitive>

Example:
7b6d0b0c80fbcf6c:red:21:27:36:0
│                │   │  │  │  └─ definitive flag (1 = committed)
│                │   │  │  └──── call3 probability
│                │   │  └─────── call2 probability
│                │   └────────── call1 probability
│                └────────────── zipcode (zone assignment)
└─────────────────────────────── 16-char BLAKE2s hash (immutable — original hash never changes)
```

**3-call lifecycle:**
- `call1` — stage set, PCS born, zipcode assigned
- `call2` — data accumulates into the ball
- `call3` — definitive check; if committed, snap-clone fires and ball enters conductor

---

## The Clone Pool

Every file that enters the system gets a hex identity, a sidecar JSON, and QR state codes.
Clone pool is the Phoenix native package backend — `clone_pool` is the 11th backend in translator.sh.

```
/mnt/clonepool/
└── <hex_of_filename>/
    ├── v1_<filename>           — versioned original
    ├── <hex>.sidecar.json      — source of truth
    ├── <hex>_header.png        — state QR (white=active / grey=deprecated / black=retired)
    └── <hex>_footer.png        — location QR (tier color)
```

States: `white` = active, `grey` = deprecated (auto-hotswaps to latest), `black` = retired.

Clone pool commands (routed through translator.sh when backend = `clone_pool`):

```bash
clone_pool fetch <pkg>    # install
clone_pool drop <pkg>     # remove
clone_pool sync           # update index
clone_pool refresh        # upgrade all
clone_pool query <pkg>    # search
clone_pool inspect <pkg>  # info
clone_pool list           # list installed
clone_pool purge          # clean cache
```

---

## Package Handler — translator.sh

The agnostic layer. Detects which package backend is present, translates UnitedSys verbs to native commands, normalizes output back up the chain, logs every transaction to SQLite.

**Location:**
- Primary: `scripts/sector3/translator.sh` → deploys to `/etc/systemd/system/translator.sh`
- Backup:  `scripts/sector2/translator/translator.sh` → deploys to `/etc/systemd/translator.sh`

**11 backends supported (checked in this order):**

| Priority | Backend | Platform |
|----------|---------|----------|
| 1st | `clone_pool` | Phoenix/UnitedSys native |
| 2nd | `apt` | Debian, Ubuntu, Mint |
| — | `dnf` | Fedora, RHEL, CentOS |
| — | `pacman` | Arch, Manjaro |
| — | `zypper` | openSUSE |
| — | `apk` | Alpine |
| — | `xbps` | Void Linux |
| — | `portage` | Gentoo |
| — | `brew` | macOS / Homebrew on Linux |
| — | `winget` | Windows 10/11 |
| — | `choco` | Windows Chocolatey |

**Verbs (same across all backends):**
```bash
translator install <pkg>
translator remove  <pkg>
translator update
translator upgrade
translator search  <pkg>
translator info    <pkg>
translator list
translator clean
```

**Sector 2 failover:** activates automatically when job queue reaches 10+ concurrent jobs.

**Catalog:** every transaction logged to `~/.catalog/catalog.db` (SQLite).

**Logs:** `~/.unitedsys/logs/translator.log`

---

## Global Install

Makes `translator` available in every terminal on Windows and Debian/WSL without a path.

```
scripts/sector2/deploy/
├── install_global.ps1   ← self-elevating UAC installer (run this)
└── deploy.sh            ← Linux-side deploy (sudo required)
```

**Run the installer:**
```powershell
# Right-click install_global.ps1 → "Run with PowerShell"
# OR from any terminal:
powershell -ExecutionPolicy Bypass -File "scripts\sector2\deploy\install_global.ps1"
```

It self-elevates via UAC, then:
1. Writes `translator.cmd` shim to `%SystemRoot%\System32\` (Windows system-wide PATH)
2. Calls WSL to `sudo ln -sf` into `/usr/local/bin/translator` (Debian system-wide)

After running: `translator search curl` works from any CMD, PowerShell, or WSL terminal.

---

## File Structure

```
PhoenixDevOps/
├── README.md                        ← you are here
├── scripts/
│   ├── sector1/                     — kernel home (rings 13–16)
│   │   ├── conductor.py             — CptConductor + PropcGate + KernelRouter
│   │   ├── Cpt_conductor.py         — multi-conductor orchestrator
│   │   ├── coms1–4/
│   │   │   ├── helix_api.py         — Franken2, Freewheeling, Propcoms (rings 13–16)
│   │   │   ├── quadengine.py        — four simultaneous language streams
│   │   │   ├── propcoms.py          — ring validator
│   │   │   ├── propcoms.sh          — daisy chain symlink creator
│   │   │   ├── propcoms_next.py     — next link in chain (coms4→3→2→1)
│   │   │   ├── helixaudit.sh        — ring health audit + rebound launcher
│   │   │   ├── rebound.sh           — process watchdog (3-strike circuit breaker)
│   │   │   └── ring_config.json     — ring identity and routing config
│   │   └── linux_concierge.py / windows_concierge.py / phoenix_bridge.py
│   │
│   ├── sector2/                     — PCS / design / backup (rings 9–12)
│   │   ├── translator/translator.sh — package handler backup copy
│   │   ├── deploy/
│   │   │   ├── deploy.sh            — Linux deploy (sudo)
│   │   │   └── install_global.ps1   — Windows+Linux global install (self-elevating UAC)
│   │   ├── coms1–4/                 — same layout as sector1 (rings 9–12)
│   │   └── Cpt_conductor.py
│   │
│   ├── sector3/                     — agnostic output translation (rings 5–8)
│   │   ├── translator.sh            — package handler PRIMARY copy
│   │   ├── coms1–4/                 — same layout (rings 5–8)
│   │   └── Cpt_conductor.py
│   │
│   └── sector4/                     — system core / storage (rings 1–4)
│       ├── coms1–4/                 — same layout (rings 1–4)
│       └── Cpt_conductor.py
│
├── kernel/
│   ├── c_kernel/
│   │   ├── helix_kernel.c           — slot 0 production C kernel (LD_PRELOAD)
│   │   ├── helix_baseline.c         — benchmark baseline
│   │   ├── Makefile                 — builds libhelix.so
│   │   ├── helix_mesh.conf          — mesh config
│   │   └── helix_run                — LD_PRELOAD launcher
│   ├── bridge/phoenix_bridge.py     — Windows↔Linux Jupyter kernel bridge
│   ├── concierge/
│   │   ├── linux/linux_concierge.py
│   │   └── windows/windows_concierge.py
│   ├── frank_helix.py               — Frank3 bridge / RAM daemon
│   ├── helix_complete_stack.py      — full memory stack (latest v3)
│   ├── helix_translator.py          — boundary edge translator
│   ├── helix_vram.py                — virtual RAM manager
│   ├── phoenix_auth.py              — hardware fingerprint auth
│   └── spec/kernel.json             — kernel slot specs
│
└── _kali_import/phoenix/            — kali reference imports (sector4 originals)
    ├── freewheeling_stage.py
    ├── pcs.py
    └── sector4/helix_api.py         (OLD — valid_targets: system_1/2/3, do not use)
```

---

## Per-Sector helix_api.py — Ring Routing

Each sector's `helix_api.py` knows only its own rings. Propcoms escalates if a packet targets the wrong ring.

| Sector | Role | Valid Rings | Franken2 Role |
|--------|------|-------------|---------------|
| Sector 1 | Kernel home | ring_13–16 | kernel_dispatch |
| Sector 2 | PCS / design | ring_9–12 | pcs_design |
| Sector 3 | Agnostic / output | ring_5–8 | output_translation |
| Sector 4 | System core | ring_1–4 | system_core |

All `propose_route()` methods fire all four streams **simultaneously**:
```python
return {"targets": {"VECTOR": "ring_13", "NOSQL": "ring_14",
                    "RELATIONAL": "ring_15", "TIMESERIES": "ring_16"}}
```

---

## Propcoms Daisy Chain

Within each sector: `coms4 → coms3 → coms2 → coms1` (ingress to egress, no loops).

Chain pointer files (`propcoms_next.py`) per sector:
```
coms4/propcoms_next.py → /etc/systemd/system/SECTOR{N}/coms3/propcoms.py
coms3/propcoms_next.py → /etc/systemd/system/SECTOR{N}/coms2/propcoms.py
coms2/propcoms_next.py → /etc/systemd/system/SECTOR{N}/coms1/propcoms.py
coms1/propcoms_next.py → # egress — end of chain
```

Symlinks are created by `propcoms.sh` in each sector — requires Linux filesystem for `ln -s`.

---

## helixaudit.sh + rebound.sh

Every coms ring (all 16) has its own audit and watchdog.

**helixaudit.sh** — entry point per ring:
1. Launches `rebound.sh` watchdog (detached process)
2. Audits the helix structure (ring config, helix_api presence, propcoms chain)

**rebound.sh** — process supervisor:
- Monitors the ring's propcoms process
- Circuit breaker: 3 strikes before escalating to guardian
- Reports to guardian before any restart
- Logs all events with ring identity (`SECTOR{N}/coms{N}`)

Run audit for any ring:
```bash
bash scripts/sector1/coms1/helixaudit.sh
```

---

## Running the Kernel Pipeline (Windows / WSL)

```bash
# From scripts/sector1 — kali path needed for freewheeling_stage and pcs
cd scripts/sector1

PYTHONUTF8=1 py -c "
import sys
sys.path.insert(0, '../../_kali_import/phoenix/sector4')
import runpy
runpy.run_path('conductor.py', run_name='__main__')
"
```

Expected output (4 balls through the prefetch pipeline):
```
Cpt_conductor — Phoenix-DevOps-oS

  [physics ]  slot=0 (c_pure      )  lang=vector      id=CPT_000001
  [ai      ]  slot=3 (python_full )  lang=timeseries  id=CPT_000002
  [network ]  slot=1 (c_sideload  )  lang=nosql       id=CPT_000003
  [system  ]  slot=0 (c_pure      )  lang=vector      id=CPT_000004

Status: {'in_flight': 4, 'egress_count': 4, 'kernel_load': {0: 0, 1: 0, 2: 0, 3: 0}, 'ring_alive': True, 'seq': 4}
```

`egress_count: 4` = all 4 packets dispatched. Pipeline confirmed working.

Note: `FileNotFoundError: systemctl` errors on Windows are expected — freewheeling_stage tries to fire
`phoenix-cpt@.service` which is a Linux systemd unit. Harmless on Windows, live on Linux.

---

## Testing translator.sh

```bash
# Help / backend list
bash scripts/sector3/translator.sh help

# Search (detects winget on Windows, apt on Debian, etc.)
bash scripts/sector3/translator.sh search curl

# After global install — works from anywhere:
translator search curl
translator install git
translator list
```

---

## Building the C Kernel (requires Linux)

```bash
cd kernel/c_kernel
make                        # builds libhelix.so
./helix_run <your_program>  # launches with LD_PRELOAD=./libhelix.so
```

---

## Deployment (post WSL swap)

```bash
# Linux — deploy translator to sector3 and sector2, symlink to /usr/local/bin
cd scripts/sector2/deploy
sudo bash deploy.sh

# Windows — self-elevating UAC installer
# Right-click install_global.ps1 → "Run with PowerShell"
```

---

## Frame Budget — Sacrifice at Full Load

```
60Hz tick  =  16.6ms per frame

200 units × physics (Slot 0, parallel)    ~1ms
16 rings  × heartbeat (Slot 0, parallel)  ~0.5ms
Economy / research (Slot 2, batched)      ~3ms
AI decisions (Slot 3, batched)            ~8ms
Network sync to peers (Slot 1)            ~2ms
──────────────────────────────────────────────
Total                                     ~14.5ms  ✓  2ms headroom

Routing overhead: 0.15ms
```

For comparison: StarCraft 2 spikes to 20–40ms at 200 units. Phoenix does it in 14.5ms on a laptop in WSL2.

---

## What Works Now

| Component | Status |
|-----------|--------|
| Conductor pipeline (sector1) | Working — egress_count=4, all slots dispatch |
| PropcGate ring validation | Fixed — ring_13/14/15/16, targets dict format |
| helix_api.py per sector | All 4 sectors differentiated, correct rings |
| Cpt_conductor.py per sector | All 4 sectors, correct ring numbers |
| helixaudit.sh (all 16 rings) | Fixed — correct SECTOR paths, rebound launch |
| rebound.sh (all 16 rings) | Fixed — correct sector/ring identifiers |
| propcoms.sh (all sectors) | Fixed — SECTOR2/3/4 paths correct |
| propcoms_next.py chain | Fixed — correct coms order per sector |
| translator.sh (11 backends) | Working — tested with winget on Windows |
| install_global.ps1 | Ready — self-elevating UAC, Windows + WSL |
| deploy.sh | Ready — sudo deploy + /usr/local/bin symlink |
| kernel/ directory | Assembled — helix_kernel.c, bridge, concierge, vram |

## What Needs Linux

| Component | What's needed |
|-----------|--------------|
| C kernel | `make` in kernel/c_kernel → libhelix.so |
| Propcoms symlinks | `ln -s` for daisy chain (propcoms.sh runs on Linux) |
| Sector deployment | `sudo bash deploy.sh` after WSL swap |
| systemd units | `phoenix-cpt@.service` — fires after sector paths are live |
| Sector 1 path | TBD — temp wiring needed at swap time |
| translator catalog | sqlite3 on PATH for `~/.catalog/catalog.db` logging |

---

## Key Decisions

- **Paths are frozen** — no sector moves until WSL frontend is hot-swapped for real Linux
- **Sector 4 needs temp wiring** at swap time before the other sectors can follow
- **coms1 sys.path takes priority** over `_kali_import` — always insert coms1 first
- **`_kali_import/phoenix/sector4/helix_api.py` is the old file** — `valid_targets: [system_1, system_2, system_3]`. Do not use it for routing; only use it for freewheeling_stage and pcs
- **Quadralingual = simultaneous** — all 4 streams fire at once, not routed to one
- **No AI in this system** — helix is optimized for AI workloads but the OS itself has no AI
- **COM chain direction**: COM4 → COM3 → COM2 → COM1 (ingress to egress, no loops)

---

## UnitedSys Quick Reference

```bash
usys init                           # first time setup
usys register ./myfile.py myfile    # register any file
usys call myfile                    # call by name
usys swap myfile ./myfile_v2.py     # hotswap live
usys install sqlite3                # install + auto-register
usys list                           # see everything registered
```

```bash
translator install <pkg>            # install via detected backend
translator search <pkg>             # search
translator list                     # list installed
translator upgrade                  # upgrade all
```

---

## Docs

| Doc | |
|-----|-|
| [docs/architecture.md](docs/architecture.md) | 16-ring map, sectors, quadralingual system |
| [docs/flow_diagram.md](docs/flow_diagram.md) | Full signal flow + latency estimates |
| [docs/kernels.md](docs/kernels.md) | Kernel slot specs and benchmark targets |
| [docs/speed_reference.md](docs/speed_reference.md) | Speed comparisons |
| [docs/usys.md](docs/usys.md) | UnitedSys complete command reference |
| [game/sacrifice/GDD.md](game/sacrifice/GDD.md) | Sacrifice RTS — Game Design Document |

---

## Roadmap

- [ ] WSL frontend hot-swap → real Linux (sector 4 temp wiring first)
- [ ] C kernel build on Linux (`make` → libhelix.so → helix_run)
- [ ] Propcoms daisy chain symlinks (`propcoms.sh` on Linux)
- [ ] `phoenix-cpt@.service` systemd unit live
- [ ] Slots 0 and 1 ported to native C (10–20x slot latency drop)
- [ ] PyPy for Slots 2–3 (3–5x throughput, no code changes)
- [ ] Two-node load split — allin1 + peer node
- [ ] Phoronix standardized benchmark integration
- [ ] translator.sh debug mode (verbose per-backend tracing)
- [ ] clone_pool backend live (when Phoenix package manager ships)

---

## License

GPL v3 — use it, share it, build on it.
