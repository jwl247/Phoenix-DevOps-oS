# Phoenix-DevOps-oS

A custom OS-level signal routing and dispatch system built for real-time performance.
Every signal — game event, system call, network packet — travels through the same deterministic path:
**Freewheeling → Captain → Propcoms → ring.** No shortcuts. No loops. No guessing.

Built to run the [Sacrifice RTS](game/sacrifice/GDD.md) at 200 units, all 16 rings, inside a 16.6ms frame budget on a laptop.

---

## What It Is

Phoenix is a quadralingual kernel — four storage languages, four kernel slots, sixteen rings across four sectors.
Every signal is born with a PCS identity (Proximity Control String) and routed by family to the correct slot.
The signal carries its own destination. Nothing looks it up mid-flight.

```
INPUT
  │
  ▼
Freewheeling Stage      — PCS born, data accumulates, snap-clone fires
  │
  ▼
Cpt_conductor           — selects kernel slot by family, wraps in QuadPacket
  │
  ▼
Propcoms                — zipcode validates, custody chain locked
  │
  ▼
coms ring (1–16)        — post-stage handler, systemd service fires
  │
  ▼
OUTPUT
```

---

## Four Kernel Slots

| Slot | Type | Language | Workloads | Target |
|------|------|----------|-----------|--------|
| 0 | c_pure | VECTOR | physics, system, collision | < 1ms / 10k pkt/s |
| 1 | c_sideload | NOSQL | network, assets, I/O | < 2ms / 5k pkt/s |
| 2 | python_user | RELATIONAL | user ops, economy, research | < 5ms / 1k pkt/s |
| 3 | python_full | TIMESERIES | AI, replay, combat log | < 10ms / 500 pkt/s |

Overflow rule: if a slot hits 100 in-flight packets, the conductor steps to the least-loaded slot automatically.

---

## Sixteen Rings — Four Sectors

```
SECTOR 4 — System Core / Storage      SECTOR 3 — Egress / State Change
  Ring  1  VECTOR  (physics)            Ring  5  egress renderer
  Ring  2  NOSQL   (network)            Ring  6  egress network
  Ring  3  RELAT.  (user/econ)          Ring  7  egress UI
  Ring  4  TSERIES (AI)                 Ring  8  egress log
  Drive-bound. Freewheeling             State change + output translation.
  holds custody.                        2x load (output + post stage).
                                        Overflow → sector 2 (whole task).

SECTOR 2 — PCS / Design / Office      SECTOR 1 — Bridge / Authority
  Ring  9  pcs creation                 Ring 13  interrupt intake
  Ring 10  rendering design             Ring 14  interrupt intake
  Ring 11  phoenix office               Ring 15  interrupt intake
  Ring 12  overflow                     Ring 16  interrupt intake
  PCS born here. Rendering design.      Input direct from interrupter.
  Phoenix Office lives here.            Bridges WSL ↔ Windows 10 Pro.
  Catches whole-task overflow           Phoenix is the authority.
  from sector 3.                        Distros are input, not law.
                                        Phoenix dictates what distros know.
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

## Components

| Component | File | Purpose |
|-----------|------|---------|
| **usys** | `sector4/usys.sh` | Universal package handler — register, hotswap, clone pool |
| **intake** | `sector4/intake.sh` | File intake — hex identity, sidecar JSON, QR state codes |
| **Freewheeling Stage** | `sector4/freewheeling_stage.py` | 3-call PCS lifecycle, snap-clone, flock grouping |
| **Cpt_conductor** | `Cpt_conductor.py` | Multi-conductor arch — one ComsConductor per ring + PeerConductor |
| **PCS** | `sector4/pcs.py` | Proximity Control String — every signal's identity |
| **Propcoms** | `sector4/helix_api.py` | Zipcode validator, ring routing, custody chain |
| **Bootstrap** | `scripts/bootstrap_node.sh` | One-shot node setup: SSH, usys, tmux, Barrier |
| **Benchmark** | `benchmark/run_benchmark.sh` | 4-condition suite: baseline / normal / stress / redline |
| **Bridge** | `kernel/bridge/phoenix_bridge.py` | Jupyter kernel — Windows↔Linux concierge |
| **Sacrifice** | `game/sacrifice/GDD.md` | The RTS game Phoenix is built to run |

---

## Quick Start

**Bootstrap a new node:**
```bash
bash scripts/bootstrap_node.sh <node_name> <peer_ip>
```

**UnitedSys (usys):**
```bash
usys init                           # first time setup
usys register ./myfile.py myfile    # register any file
usys call myfile                    # call it by name
usys swap myfile ./myfile_v2.py     # hotswap live
usys install sqlite3                # install + auto-register
usys list                           # see everything
```

**Run the kernel pipeline:**
```bash
cd sector4
python3 conductor.py
```

**Run benchmarks:**
```bash
bash benchmark/run_benchmark.sh baseline    # idle, full resources
bash benchmark/run_benchmark.sh normal      # realistic daily load
bash benchmark/run_benchmark.sh stress      # saturated, peak load
bash benchmark/run_benchmark.sh redline     # 200 units, all 16 rings
bash benchmark/run_benchmark.sh all         # all four conditions
```

---

## PCS — Proximity Control String

Every signal gets a PCS identity at birth. It travels with the signal forever.

```
<hash>:<zipcode>:<p1>:<p2>:<p3>:<definitive>

Example:
7b6d0b0c80fbcf6c:red:21:27:36:0
│                │   │  │  │  └─ definitive flag
│                │   │  │  └──── call3 probability
│                │   │  └─────── call2 probability
│                │   └────────── call1 probability
│                └────────────── zipcode (zone assignment)
└─────────────────────────────── 16-char BLAKE2s hash (immutable)
```

3-call lifecycle: `call1` → stage set → `call2` → data accumulates → `call3` → definitive check → snap-clone fires.

---

## The Clone Pool

Every file that enters the system gets a hex identity, a sidecar JSON, and QR state codes.

```
/mnt/clonepool/
└── <hex_of_filename>/
    ├── v1_<filename>           — versioned file
    ├── <hex>.sidecar.json      — source of truth
    ├── <hex>_header.png        — state QR (white / black / grey)
    └── <hex>_footer.png        — location QR (tier color)
```

States: `white` = active, `grey` = deprecated (auto-hotswaps), `black` = retired.

---

## Docs

| Doc | |
|-----|-|
| [docs/architecture.md](docs/architecture.md) | 16-ring map, sectors, quadralingual system |
| [docs/flow_diagram.md](docs/flow_diagram.md) | Full signal flow + latency estimates |
| [docs/kernels.md](docs/kernels.md) | Kernel slot specs and benchmark targets |
| [docs/speed_reference.md](docs/speed_reference.md) | Speed comparisons — what the numbers mean |
| [docs/usys.md](docs/usys.md) | UnitedSys complete command reference |
| [game/sacrifice/GDD.md](game/sacrifice/GDD.md) | Sacrifice RTS — Game Design Document |

---

## Roadmap

- [ ] Slots 0 and 1 ported to native C (10–20x slot latency drop)
- [ ] PyPy for Slots 2–3 (3–5x throughput, no code changes)
- [ ] Bare metal Linux deployment (drop WSL2 overhead)
- [ ] Two-node load split — allin1 + peer node
- [ ] `phoenix-cpt@.service` systemd unit installation (sector3/systemd)
- [ ] Phoronix standardized benchmark integration

---

## License

GPL v3 — use it, share it, build on it.
