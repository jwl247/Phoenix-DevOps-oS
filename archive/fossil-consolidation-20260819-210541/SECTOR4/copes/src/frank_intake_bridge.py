#!/usr/bin/env python3
"""
frank_intake_bridge.py — Phoenix DevOps OS / CoPES
Thin bridge: intake.sh calls this after a successful intake operation.
Frank logs the event via coordinate() and registers intake as a sideload.
Does NOT replace intake.sh logic — Frank observes, intake.sh owns the pipeline.

Usage:
  python3 frank_intake_bridge.py <action> <source> <destination> [tav] [name] [version]

Actions:
  intake        — file intaked into clonepool
  clone_out     — file cloned out of clonepool
  dir_intake    — directory intaked
  backend       — package registered from backend
  self_register — intake script self-registered

jwl247 / United Systems / GPL v3
"""

import sys
import os
from pathlib import Path

PHOENIX_HOME = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))
sys.path.insert(0, str(PHOENIX_HOME / "src"))

def main():
    args = sys.argv[1:]

    if len(args) < 3:
        print("Usage: frank_intake_bridge.py <action> <source> <destination> [tav] [name] [version]")
        sys.exit(1)

    action      = args[0]
    source      = args[1]
    destination = args[2]
    tav         = args[3] if len(args) > 3 else ""
    name        = args[4] if len(args) > 4 else source
    version     = args[5] if len(args) > 5 else "unknown"

    try:
        import frank

        frank.init_db()

        frank.sideload(
            name="intake",
            process="intake.sh",
            version="1.6.0"
        )

        frank.coordinate(
            source=source,
            destination=destination,
            payload={
                "action":  action,
                "name":    name,
                "tav":     tav,
                "version": version,
            }
        )

        print(f"[frank:bridge] {action} → coordinated: {name} ({tav})")

    except ImportError as e:
        print(f"[frank:bridge] frank not available — skipping: {e}")
        sys.exit(0)

    except Exception as e:
        print(f"[frank:bridge] warning: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
