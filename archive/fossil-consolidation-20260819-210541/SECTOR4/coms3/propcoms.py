#!/usr/bin/env python3
"""
propcoms.py — Comms Ring 3 Propagator / Leech Module
Phoenix DevOps OS / Sector 4
"""

import os
import sys
import time
import json
import shutil
import logging
from pathlib import Path

# Safe UTF-8 console output
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

JONAS_ROOT = Path(f"/mnt/breach_coms3/jonas" if os.name != 'nt' else f"C:/Phoenix/coms3/jonas")
STAGING    = Path(f"/tmp/staging_coms3" if os.name != 'nt' else f"C:/Phoenix/staging3")
PORTAL     = Path(f"/tmp/portal_coms3" if os.name != 'nt' else f"C:/Phoenix/portal3")

class PropagatorLeech:
    def __init__(self, host_name=f"coms3"):
        self.host_name = host_name
        self.running = True
        self.id_registry = {}
        self.tuning = {
            "chunk_size": 65536,
            "reset_threshold": 3,
            "total_cycles": 0,
            "last_snap_ms": 0.0
        }
        STAGING.mkdir(parents=True, exist_ok=True)
        PORTAL.mkdir(parents=True, exist_ok=True)

    def update_tuning(self, key, val):
        self.tuning[key] = val

    def execute_snap(self, data):
        primary_id = data.get("primary_id", "default")
        node_id    = data.get("node_id", "0")
        dest       = data.get("dest")
        start_time = time.time()

        node_path = JONAS_ROOT / f"jonas_raw_{node_id}"

        # 3-Strike Counter for this ID
        self.id_registry[primary_id] = self.id_registry.get(primary_id, 0) + 1
        hits = self.id_registry[primary_id]

        try:
            # Stage 1: Ingest (.buf1)
            b1, b2, b3 = STAGING / ".buf1", STAGING / ".buf2", STAGING / ".buf3"
            if node_path.exists():
                with open(node_path, 'rb') as src, open(b1, 'wb') as dst:
                    dst.write(src.read(self.tuning.get('chunk_size', 65536)))

                # Stage 2 & 3: Versioning & Profile Lock
                shutil.copy2(b1, b2)
                shutil.copy2(b2, b3)
                if dest:
                    shutil.copy2(b3, dest)

            # Metrics & Self-Adjustment
            duration_ms = (time.time() - start_time) * 1000
            self.update_tuning('last_snap_ms', duration_ms)
            self.update_tuning('total_cycles', self.tuning.get('total_cycles', 0) + 1)

            if hits >= self.tuning.get('reset_threshold', 3):
                self.id_registry[primary_id] = 0
                return True
            return False

        except Exception as e:
            logging.error(f"[LEECH-coms3] Snap Error: {e}")
            return False

    def run(self):
        logging.info(f"🧬 Propagator Leech attached to {self.host_name}. Monitoring Door...")
        while self.running:
            for ball in PORTAL.glob("*.json"):
                try:
                    with open(ball, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.execute_snap(data)
                    ball.unlink(missing_ok=True)
                except Exception as e:
                    logging.error(f"[LEECH-coms3] Ball Error: {e}")
            time.sleep(0.1)

    def stop(self):
        self.running = False


# ============================================================
# INTEGRATION WITH NEW CONNECTIONS SYSTEM
# ============================================================
"""
The canonical connections system (SECTOR4/connections.py) provides:
- register_from_dispatch()
- daisy_relay()
- health_check_all()
- Syncthing + ZMQ helpers
- Glossary publishing
"""

try:
    from connections import get_connections as _get_phoenix_connections
    PHOENIX_CONNECTIONS = _get_phoenix_connections()
except Exception:
    PHOENIX_CONNECTIONS = None

def relay_via_connections(payload: dict):
    """Preferred relay once connections system is wired everywhere."""
    if PHOENIX_CONNECTIONS:
        return PHOENIX_CONNECTIONS.daisy_relay(payload)
    return {"status": "fallback", "payload": payload}


"""
[HELIX BOOTSTRAP]
Initializing Peer Modules...
• Loading declaration cards
• Registering ST / LE / PE / COMS roles
• Binding IDENT and GEN lineage
• Attaching Leeches to ingress paths
• Sync handoff to Frank

All peers online.
Helix modules registered and ready.
"""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    leech = PropagatorLeech()
    logging.info(f"Comms Ring 3 Propagator initialized.")
