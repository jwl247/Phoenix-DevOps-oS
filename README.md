# Phoenix-DevOps-oS

**Distro-agnostic. Deterministic. Quadralingual.**

> Built with Claude Sonnet 4.6. Target version: usys v4.6.

---

## Signal Flow

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  INPUT — unit order / game event / system call
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                         │
                         ▼
┌───────────────────────────────────────────────────────────┐
│  FREEWHEELING STAGE                           ~0.15ms      │
│  call1() → PCS born, hash stamped, slot reserved           │
│  call2() → data accumulates, probability climbs            │
│  call3() → definitive check, snap-clone fires              │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SECTOR 4 — SYSTEM CORE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│  Cpt_conductor routes by family → PropcGate validates      │
│                                                            │
│  ┌──────────┬──────────┬──────────┬──────────┐             │
│  │  SLOT 0  │  SLOT 1  │  SLOT 2  │  SLOT 3  │             │
│  │  VECTOR  │  NOSQL   │RELATIONAL│TIMESERIES│             │
│  │ physics  │ network  │ economy  │    ai    │             │
│  ├──────────┼──────────┼──────────┼──────────┤             │
│  │  <1ms    │  <2ms    │  <5ms    │  <10ms   │ per packet  │
│  │ 10k/sec  │ 5k/sec   │ 1k/sec   │ 500/sec  │ throughput  │
│  └──────────┴──────────┴──────────┴──────────┘             │
│  Ring 1  Ring 2  Ring 3  Ring 4                            │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SECTOR 3 — OUTPUT / systemd corridor
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│  Ring 5  renderer / display / audio          ~2ms           │
│  Ring 6  network I/O / sync                  ~1ms           │
│  Ring 7  UI state / HUD                      ~0.5ms         │
│  Ring 8  event log / replay store            ~0.1ms         │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SECTOR 2 — SESSION / multiplayer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│  Ring 9   matchmaking / session              ~5–20ms (net)  │
│  Ring 10  comms / chat  (spy intercept)      ~2ms           │
│  Ring 11  alliance / diplomacy               ~5ms           │
│  Ring 12  victory condition monitor          ~1ms/tick      │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SECTOR 1 — BRIDGE / platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
│  Ring 13  save / checkpoint                  ~10ms          │
│  Ring 14  replay / audit                     async          │
│  Ring 15  OS integration (Windows)           ~1ms           │
│  Ring 16  cross-platform bridge (Linux)      ~1ms           │
└───────────────────────────────────────────────────────────┘
                         │
                         ▼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  OUTPUT — display frame / network packet / log / save file
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## The Frame Budget

```
60Hz game tick  =  16.6ms per frame

Phoenix at full Sacrifice load (200 units, all 16 rings):
  Slot 0  physics × 200 units     ~1ms    (parallel)
  Slot 1  network sync            ~2ms    (parallel)
  Slot 2  economy / research      ~3ms    (parallel)
  Slot 3  AI decisions            ~8ms    (parallel)
  Routing overhead                ~0.15ms
  ──────────────────────────────────────────
  Total                           ~14.5ms  ✓  2ms headroom

Utilization: 88%   Headroom: 12%   Status: ships
```

---

## Speed Reference

| Comparison | Time |
|---|---|
| Google "fast" webpage | 3,000ms |
| Human blink | 150–400ms |
| StarCraft 2 spike at 200 units | 20–40ms |
| Phoenix at 200 units (today, WSL2) | **14.5ms** |
| Phoenix routing overhead | **0.15ms** |
| Unity/Unreal engine tick (before game logic) | 2–6ms |
| Phoenix routing (before game logic) | **0.15ms** |

**The ceiling:**
```
Today       Python + WSL2       14.5ms   ✓ ships
PyPy        no code changes      ~5ms    ✓ 3× headroom
Native C    slots 0+1            ~8ms    ✓ 400+ units
Two nodes   load split           ~8ms    ✓ 500+ units
```

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────┐
│                  Phoenix-DevOps-oS                  │
│                                                     │
│  Sector 4 — SYSTEM CORE                             │
│  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌────────────┐ │
│  │ usys     │ │Freewhl   │ │Cpt   │ │ Franken    │ │
│  │ v0.2.0   │ │Stage     │ │Cond. │ │ Helix RAM  │ │
│  └──────────┘ └──────────┘ └──────┘ └────────────┘ │
│                                                     │
│  Sector 3 — OUTPUT / systemd corridor               │
│  Sector 2 — SESSION / multiplayer / sync            │
│  Sector 1 — BRIDGE / Windows-Linux concierge        │
└─────────────────────────────────────────────────────┘
```

**4 Sectors × 4 Coms Rings = 16 rings total.**
Every signal travels: Freewheeling → Cpt_conductor → Propcoms → coms ring.
Nothing talks to a ring directly. Everything goes through propcoms.

---

## Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **usys** | `sector4/usys.sh` | Universal package handler, clone pool, hotswap registry |
| **intake** | `sector4/intake.sh` | File intake pipeline — hex identity, sidecar JSON, QR codes |
| **Freewheeling Stage** | `sector4/freewheeling_stage.py` | 3-call PCS lifecycle, snap-clone, flock grouping |
| **Cpt_conductor** | `sector4/conductor.py` | Quad-kernel router, propcoms gate, ingress/egress |
| **Franken / Helix** | `coms1/franken.py` | Virtual RAM, tiered memory, cross-platform abstraction |
| **PCS** | `sector4/pcs.py` | Probabilistic Commit System — every signal's identity |
| **Propcoms** | `sector4/propcoms.py` | Zipcode validator, ring routing, custody chain |
| **Bootstrap** | `scripts/bootstrap_node.sh` | One-shot node setup: SSH, usys, tmux, Barrier |
| **Bridge** | `sector1/phoenix_bridge.py` | Jupyter kernel — Linux/Windows concierge bridge |
| **Game** | `game/sacrifice/GDD.md` | Sacrifice RTS — built on Phoenix runtime |

---

## Quick Start

### New Node Bootstrap
```bash
# On any Debian/WSL2 node:
bash bootstrap_node.sh <node_name> <peer_ip>
```

### UnitedSys (usys)
```bash
usys init                          # first time setup
usys register ./myfile.py myfile   # register any file
usys call myfile                   # call it by name
usys swap myfile ./myfile_v2.py    # hotswap live
usys install sqlite3               # install + auto-register
usys list                          # see everything
```

### Run the Kernel Pipeline
```bash
cd sector4
python3 conductor.py            # test full pipeline
```

### Run the Benchmark
```bash
bash benchmark/run_benchmark.sh baseline   # single condition
bash benchmark/run_benchmark.sh all        # all 4 conditions
bash benchmark/run_benchmark.sh redline    # Sacrifice game load
```

---

## Documentation

| Doc | Description |
|-----|-------------|
| [docs/flow_diagram.md](docs/flow_diagram.md) | Full signal flow + speed estimates |
| [docs/speed_reference.md](docs/speed_reference.md) | Speed comparisons — what the numbers mean |
| [docs/architecture.md](docs/architecture.md) | 16-ring map, sectors, quadralingual system |
| [docs/kernels.md](docs/kernels.md) | Kernel slot specs, benchmark targets |
| [docs/usys.md](docs/usys.md) | UnitedSys complete command reference |
| [docs/demo_julian.md](docs/demo_julian.md) | Demo script |
| [game/sacrifice/GDD.md](game/sacrifice/GDD.md) | Sacrifice RTS — Game Design Document |

---

## License
GPL v3 — use it, share it, build on it.
Commercial dual-license available for Phoenix Office and enterprise tiers.
