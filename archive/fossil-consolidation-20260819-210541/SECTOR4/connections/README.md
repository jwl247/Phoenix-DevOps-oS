# Phoenix Connections System

Canonical implementation for all wiring, coms, and peer/device communication.

**File**: `SECTOR4/connections.py`

## Quick Start

```python
from connections import get_connections

cm = get_connections()
cm.register_from_dispatch("../sector2/propagator/dispatch.json")
cm.register_from_helix_mesh("../sector1/helix/conf/helix_mesh.conf")

print(cm.summary())
cm.daisy_relay({"action": "propagate", "data": "something"})
cm.health_check_all()
cm.publish_to_glossary()  # if PHOENIX_AUTH set
```

## What it wires

- ZMQ mesh (frank-helix, romeo/juliet, frank3, propcoms COM ports)
- dispatch.json targets (vault, sql, d1, frank3, peer, windows)
- helix_mesh.conf ports
- Syncthing devices (REST + ensure)
- HTTP / worker / D1 endpoints
- COM daisy chain relay (COM4→3→2→1)
- "Friendships" (guardian style)
- Local sqlite catalog + optional D1 glossary (category=connection)
- Diagnostics with required "What + Why + Recommended Action"

## Integration points

- propcoms.py (coms layers) can call relay_via_connections
- Conductor / SyncEngine can use ConnectionManager for destinations
- Intake can register new connection configs (sidecar + glossary)
- Dashboard / status can query cm.list_connections()
- packages-worker glossary gains "connection" entries

## Status (2026-06-30)

🆕 Core implemented as part of Phase 1 (Connections & Wiring) from Lost_Ark_Implementation_Outline.

Next steps (future):
- Full ZMQ socket send/recv wrappers
- Real Syncthing folder/device management via API
- Auto-registration on intake of .connection.json files
- C bindings for Helix fast path
- Background service using this

See also:
- Lost_Ark_Connections_Wiring_Map.md
- Phoenix_Structure_and_Connections.md
- dispatch.json
- helix_mesh.conf
- The big PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md (updated)
