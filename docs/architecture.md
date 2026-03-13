# Phoenix-DevOps-oS — System Architecture

## The Ring System

**4 Sectors × 4 Coms Rings = 16 rings total.**

```
SECTOR 4 — SYSTEM CORE
  coms1  Ring 1   VECTOR      c_pure        max speed, peak traffic
  coms2  Ring 2   NOSQL       c_sideload    balanced, extended calls
  coms3  Ring 3   RELATIONAL  python_user   flexible, moderate load
  coms4  Ring 4   TIMESERIES  python_full   full flexibility, AI/dev

SECTOR 3 — OUTPUT / systemd corridor
  coms1  Ring 5   renderer output, display, audio
  coms2  Ring 6   network I/O, sync
  coms3  Ring 7   UI state, HUD
  coms4  Ring 8   event log, replay

SECTOR 2 — SESSION
  coms1  Ring 9   multiplayer session, matchmaking
  coms2  Ring 10  comms, chat (spy intercept hooks here)
  coms3  Ring 11  alliance / diplomacy
  coms4  Ring 12  victory condition monitor

SECTOR 1 — BRIDGE / Platform
  coms1  Ring 13  save / checkpoint
  coms2  Ring 14  replay / audit
  coms3  Ring 15  OS integration (Windows concierge)
  coms4  Ring 16  cross-platform bridge (Linux concierge)
```

---

## Signal Flow — No Shortcuts

Every signal follows the same path. No ring is ever addressed directly.

```
INPUT
  │
  ▼
Freewheeling Stage
  call1() — PCS born, slot reserved, flock assigned by zipcode
  call2() — data accumulates in warm storage
  call3() — definitive check → snap-clone fires
  │
  ▼
Cpt_conductor (Captain)
  select_slot()  — family → preferred kernel slot (0-3)
  QuadPacket     — data wrapped in quadralingual packet
  PropcGate      — zipcode validates, custody chain preserved
  │
  ▼
Propcoms (zipcode validator)
  validate()     — packet cleared for target ring
  tick()         — heartbeat, custody chain update
  ring_alive()   — liveness check
  │
  ▼
coms ring (1-16)
  post-stage handler
  systemd service: phoenix-cpt@<hash>.service
```

---

## Sectors

### Sector 4 — System Core
The brain. Everything starts here. All core system files live here.
- `usys.sh` — universal package handler
- `conductor.py` — captain, quad-kernel router
- `freewheeling_stage.py` — 3-call PCS lifecycle
- `pcs.py` — probabilistic commit system
- `propcoms.py` — zipcode validator, ring routing
- `intake.sh` — clone pool intake pipeline

### Sector 3 — Output / systemd Corridor
The output layer. Sector 3 is in the systemd corridor — everything that leaves the system (display, audio, network write, log write) goes through here.

### Sector 2 — Session
Multiplayer sessions, matchmaking, sync, comms. The layer that connects nodes.

### Sector 1 — Bridge
The Windows↔Linux bridge. The concierge layer. `phoenix_bridge.py` runs as a Jupyter kernel, bridging the two sides. `windows_concierge.py` and `linux_concierge.py` are the two halves.

---

## The Quadralingual Rule

**Data in Phoenix custody stays quadralingual.**
The language is never stripped from the packet. It travels with the signal through every ring.

```
VECTOR      — float array    — physics, system, collision
NOSQL       — flat dict      — network, assets, key-value
RELATIONAL  — typed dict     — user ops, economy, schema data
TIMESERIES  — list of events — AI, replay, audit, combat log
```

Each QuadPacket can express its data natively in any of the four languages:
```python
packet.as_vector()      # → [float, float, ...]
packet.as_nosql()       # → {"id": ..., "pcs": ..., "data": ...}
packet.as_relational()  # → {"id": ..., "pcs": ..., "ts": ..., "val": ...}
packet.as_timeseries()  # → [{"ts": ..., "metric": ..., "pcs": ..., "val": ...}]
packet.native()         # → in the packet's own language
```

---

## Node Identity

Each bootstrapped node writes `~/.usys/node.json`:
```json
{
  "node_name": "allin1",
  "user": "jwl247",
  "hostname": "DESKTOP-ALLIN1",
  "pubkey": "ssh-ed25519 ...",
  "bootstrapped_at": "2026-03-12T00:00:00Z",
  "peer_ip": "192.168.1.108",
  "pool_root": "/mnt/clonepool"
}
```

Nodes find each other via SSH key trust + tmux shared session. Barrier handles shared keyboard/mouse across machines.

---

## Clone Pool

The operational file database. Trickle-down versioning. Every file that enters the system gets:
- A hex identity (filename → hex)
- A sidecar JSON (source of truth)
- A header QR (state: white/black/grey)
- A footer QR (location: tier + color)
- A version entry in usys DB

Max depth: 4 folders. Each folder = one tier. Deeper = more archival.
