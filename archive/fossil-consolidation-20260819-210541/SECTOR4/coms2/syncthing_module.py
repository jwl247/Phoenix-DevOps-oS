#!/usr/bin/env python3
"""
syncthing_module.py — Python bridge for HeIX Syncthing Distribution Module
Phoenix DevOps OS / Sector 4
"""

import os
import sys
import subprocess
from pathlib import Path

MODULE_JS = Path(__file__).parent / "syncthing_module.js"

class SyncthingDistributionModule:
    """Python bridge to HeIX Syncthing Distribution Module (syncthing_module.js)."""
    def __init__(self, role="master", port=8384):
        self.role = role
        self.port = port

    def run_node_sync(self):
        if not MODULE_JS.exists():
            return {"status": "error", "message": "syncthing_module.js not found"}
        try:
            res = subprocess.run(["node", str(MODULE_JS)], capture_output=True, text=True, timeout=30)
            return {"status": "ok", "returncode": res.returncode, "stdout": res.stdout, "stderr": res.stderr}
        except Exception as e:
            return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    mod = SyncthingDistributionModule()
    print(f"Syncthing Distribution Module Bridge online (Role: {mod.role}, Port: {mod.port})")
